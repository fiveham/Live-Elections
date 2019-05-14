import requests
import time
import datetime
import subprocess
import json
import os
import random

SUMMARY_VERSION = "2019.5.14"

def now_tuple():
  now = datetime.datetime.now()
  return (now.year, now.month, now.day, now.hour, now.minute)

def intervals():
  for x in (10,8,6,4):
    yield x
    yield x
  while True:
    yield 2

def top1(list, pty, test=None, after=(lambda x: x)):
  if test is None:
    test = lambda dic : dic['pty'] == pty
  top = max(list, key=(lambda d : (int(d['vct'])
                                   if test(d)
                                   else -1)))
  return after(top)

def top2(list, pty):
  top = top1(list, pty, after=(lambda x: x['bnm']))
  sec = max(list, key=(lambda d : (int(d['vct'])
                                   if d['bnm'] != top and d['pty'] == pty
                                   else -1)))
  return [top,sec['bnm']]

class AutoDown:
  
  def __init__(
      self,
      date_string,
      id_to_COUNTY,
      repo_path,
      cache_path='./cache/',
      simulator=None,
      filter=(lambda x : x)):
    
    if cache_path and simulator:
      raise Exception(("Simulating by reading a cache and then also writing "
                       "into that cache would be a bad idea."))
    #if cache_path is falsey, step-by-step results are not cached
    self.base_url = 'https://er.ncsbe.gov/enr/%s/data/' % date_string
    self.id_to_COUNTY = dict(id_to_COUNTY)
    self.repo_path = repo_path[:-1] if repo_path.endswith('/') else repo_path
    self.cache_path = ((cache_path + '/') 
                       if cache_path and not cache_path.endswith('/') 
                       else cache_path)
    self.getter = simulator or self
    self.filter = filter
    self.now_ish = None
    self.names_by_party = None
  
  
  def cache_it(self, label, cache_me):
    if not self.cache_path:
      return
    with open(self.cache_path + label +
              '_%d-%d-%d-%d-%d.txt' % self.now_ish, 'w') as into:
      json.dump(cache_me, into)
  
  def get_tops(self, list, tops):
    #partition list by party
    result = {pty:[d
                   for d in list
                   if d['bnm'] in self.names_by_party[pty]]
              for pty in self.names_by_party}
    topdic = {}
    for pty in result:
      t = top1(
        list,
        pty,
        test=(lambda dic : dic['bnm'] in self.names_by_party[pty]))
      p = pty[0]
      top2p = tops[p]
      name = t['bnm']
      if t['vct'] == '0':
        topdic[p] = -1
      else:
        try:
          topdic[p] = top2p.index(name)
        except ValueError: #name not in list
          topdic[p] = 2
    return topdic
  
  def partition_by_precinct(self, county_results_by_precinct, tops):
    result = {d['aid']:[] for d in county_results_by_precinct}
    for d in county_results_by_precinct:
      precinct_name = d['aid']
      result[precinct_name].append(d)
    
    for precinct_name in result:
      prec_el_results = result[precinct_name]
      g = self.get_tops(prec_el_results, tops)
      d = {'top': g}
      result[precinct_name] = d
    return result
  
  #summary
  def distill_results(self, state, county, prec, is_final):
    distilled = {
      'version': SUMMARY_VERSION, 
      'updated': "-".join(str(x) for x in self.now_ish),
      'isFinal': is_final or "",
    }
    
    if all(d['vct'] == '0' for d in state):
      return distilled
    
    tops = {pty[0]:top2(state, pty) for pty in self.names_by_party}
    
    votes = {}
    for p,names in tops.items():
      votes_in_party = []
      for i in range(2):
        cand = tops[p][i]
        d = next(iter(e for e in state if e['bnm'] == cand))
        entry = {'count'  : int(d['vct']),
                 'percent': float(d['pct'])}
        votes_in_party.append(entry)
      else:
        entry = {'count'  : sum(int(d['vct'])
                                for d in state
                                if (d['pty'][0] == p and
                                    d['bnm'] not in tops[p])),
                 'percent': sum(float(d['pct'])
                                for d in state
                                if (d['pty'][0] == p and
                                    d['bnm'] not in tops[p]))}
        votes_in_party.append(entry)
      votes[p] = votes_in_party
    
    the_rest = {
      'top': tops,
      'votes': votes, 
      'by_county': {
        self.id_to_COUNTY[cId]: {
          'top': self.get_tops(county[cId], tops),
          'by_precinct': self.partition_by_precinct(prec[cId], tops),
        }
        for cId in county
      }
    }
    
    distilled.update(the_rest)
    return distilled
  
  def push_it(self):
    print("Pushing summary to github")
    subprocess.run('git add summary.txt'.split(), cwd=self.repo_path)
    
    commit_msg = 'result summary %d-%d-%d-%d-%d' % self.now_ish
    commit_cmd = 'git commit -m'.split() + [commit_msg]
    subprocess.run(commit_cmd, cwd=self.repo_path)
    
    subprocess.run('git push'.split(), cwd=self.repo_path)
  
  def upload(self, state, county, prec, is_final):
    distilled = self.distill_results(state, county, prec, is_final)
    with open(self.repo_path + '/summary.txt', 'w') as into:
      json.dump(distilled, into)
    self.push_it()
    
    print()
    q = str(distilled)
    if len(q) <= 500:
      print(q)
    else:
      i = random.randint(0,len(q)-1-500)
      print(q[i:i+500])
    print()
  
  def fetch(self, label, countyID, now_ish):
    y,l,d,h,m = now_ish
    return requests.get(
        self.base_url + label + '_%d.txt?v=%d-%d-%d' % (countyID,d,h,m)
        ).json()
  
  #TODO check whether there even are changes to add/commit/push first
  def sync(self):
    subprocess.run("git add .".split(), cwd=self.repo_path)
    
    commit_msg = 'handle changes before autoloading'
    commit_cmd = 'git commit -m'.split() + [commit_msg]
    subprocess.run(commit_cmd, cwd=self.repo_path)
    
    subprocess.run('git pull'.split(), cwd=self.repo_path)
    subprocess.run('git push'.split(), cwd=self.repo_path)
  
  #method for simulator
  def get_county(self, countyId, now_ish):
    return self.fetch('results', countyId, now_ish)
  
  #method for simulator
  def get_state_results(self, now_ish):
    return self.get_county(0, now_ish)
  
  #method for simulator
  def get_precincts(self, countyId, now_ish):
    return self.fetch('precinct', countyId, now_ish)
  
  #method for simulator
  def get_prec0(self, now_ish):
    return self.get_precincts(0, now_ish)
  
  #method for simulator
  def lights_out(self, now_ish):
    return now_ish[-2] == 0 #If the operating "now" minute is 12:XX a.m.
  
  def run(self):
    #self.sync()
    
    prev_state_results = None
    prev_prec0 = None
    
    while True:
      right_now_ish = now_tuple()
      prev_minute = right_now_ish[-1]
      
      cacheable_state_results = self.getter.get_state_results(right_now_ish)
      cacheable_prec0 = self.getter.get_prec0(right_now_ish)
      
      state_results = self.filter(cacheable_state_results)
      prec0 = self.filter(cacheable_prec0)
      
      self.names_by_party = (
          self.names_by_party or
          {party:[e['bnm'] for e in state_results if e['pty'] == party]
           for party in {d['pty'] for d in state_results}})
      
      if state_results != prev_state_results or prec0 != prev_prec0:
        print("Change of state")
        prev_state_results = state_results
        prev_prec0 = prec0
        
        self.now_ish = right_now_ish
        
        cacheable_counties  = {
            NAME:self.getter.get_county(countyId, self.now_ish)
            for countyId,NAME in self.id_to_COUNTY.items()}
        cacheable_precincts = {
            NAME:self.getter.get_precincts(countyId, self.now_ish)
            for countyId,NAME in self.id_to_COUNTY.items()}
        
        counties  = {countyId:self.filter(cacheable_counties[NAME])
                     for countyId,NAME in self.id_to_COUNTY.items()}
        precincts = {countyId:self.filter(cacheable_precincts[NAME])
                     for countyId,NAME in self.id_to_COUNTY.items()}
        
        self.cache_it("state",     cacheable_state_results)
        self.cache_it("precinct0", cacheable_prec0)
        self.cache_it("counties",  cacheable_counties)
        self.cache_it("precincts", cacheable_precincts)
        
        is_final = all(all('final' in d[x].lower()
                           for x in ('sta','cts'))
                       for d in prec0)
        
        self.upload(state_results, counties, precincts, is_final)
        
        if is_final:
          print("All precincts reported. Done.")
          return
      
      if self.getter.lights_out(right_now_ish):
        print("Terminating because this has just gone on too long.")
        summary = None
        with open(self.repo_path + '/summary.txt', 'r') as out:
          summary = json.load(out)
        summary['isFinal'] = "Terminated for time."
        with open(self.repo_path + '/summary.txt', 'w') as into:
          json.dump(summary, into)
        self.push_it()
        return
      else:
        #Wait 10s twice, 8s twice, etc. until 2s each time.
        #Once you're in the next minute, loop back around.
        print('waiting till next min')
        for interval in intervals():
          m = now_tuple()[-1]
          if m != prev_minute:
            print()
            print('='*75)
            print("Doing it again: " + str(m))
            break #out of for-loop, repeating while-loop
          time.sleep(interval)

#TODO put in actual documentation describing what each __init__ parameter does
class FromCache:
  def __init__(self, cache_dir, sim_start, id_to_COUNTY):
    self.cache_dir = cache_dir if cache_dir.endswith('/') else cache_dir+'/'
    
    #When this simulation starts, it will pretend that that moment is the
    #moment represented by sim_start
    self.sim_start = sim_start
    
    self.id_to_COUNTY = dict(id_to_COUNTY)
    
    #The actual moment in time when this simulation begins running.
    #This will be set when any of the three interface methods is first called.
    self.op_start = None 
    
    #Identify each minute described in the cache, and map from each label to
    #a sorted list of the minutes for which there exists a file matching that
    #label.
    self.cache_minutes = {
        label:sorted(tuple(int(n)
                           for n in file[1+file.index('_'):-4].split('-'))
                     for file in os.listdir(self.cache_dir)
                     if file.startswith(label))
        for label in ('state','counties','precincts','precinct0')}
    
    #cache key and value for json-loading hard drive cache files
    self.runtime_cache = {}
  
  def simulation_moment(self, now_ish):
    now = datetime.datetime( *now_ish )
    diff = now - self.op_start
    then = self.sim_start + diff
    return (then.year, then.month, then.day, then.hour, then.minute)
  
  def before(self, label, sim_moment):
    if sim_moment in self.cache_minutes[label]:
      return sim_moment
    else:
      return next(iter(minute
                       for minute in reversed(self.cache_minutes[label])
                       if minute < sim_moment),
                  #if simulation moment before all results, use earliest results
                  next(iter(self.cache_minutes[label])))
  
  def set_op_start(self, now_ish):
    self.op_start = self.op_start or datetime.datetime( *now_ish )
  
  def get_from_cache(self, label, now_ish):
    self.set_op_start(now_ish)
    simmom = self.simulation_moment(now_ish)
    #if there's no cache result at simmom exactly, then retrieve the cache
    #result from the most recent prior minute, since that's what would have
    #been available in while running the script for real during the election
    #night.
    cache_moment = self.before(label, simmom)
    
    if (label in self.runtime_cache and
        self.runtime_cache[label][0] == cache_moment):
      return self.runtime_cache[label][1]
    
    print("Sim moment  : "+str(simmom)+'\t'+label)
    print("cache moment: "+str(cache_moment)+'\t'+label)
    
    val = None
    with open(
        self.cache_dir + label + "_%d-%d-%d-%d-%d.txt" % cache_moment,
        'r') as outof:
      val = json.load(outof)
    self.runtime_cache[label] = [cache_moment, val]
    return val
  
  #Return statements for get_county and get_precincts end with
  #[self.id_to_COUNTY[countyId]] because the cache files use county names (in
  #all-caps) as human-readable identifiers for counties while the in-memory
  #data structures use int county ID numbers as identifiers instead. ID numbers
  #are used during the non-human-readable parts of the process because the
  #files that need to be downloaded from the NSCBE (during non-simulated runs)
  #use number IDs for counties. In order to make correct get-requests for those
  #files, we have to either use county ID numbers internally and stringify them
  #in the requested file names or use county names internaly and translate them
  #into ID numbers when it's time to make a request.
  #Part of this project used to be a plan to simply save, commit, and push files
  #from the NCSBE to Github, using one local machine as a mirror to just bounce
  #the files onto the same domain as the live map page. Saving those files with
  #the same name structure as they had on the NCSBE system, using county ID
  #numbers, would be easier using ID numbers internally rather than potentially
  #having to go from name to number twice or more depending on how the local
  #file-saving code ultimately ended up structured. Even worse, converting the
  #name to a number just once and then passing that number around as a parameter
  #through several function calls would require adding a lot of messiness to the
  #code. Using a number ID for each county internally was simply the cleanest of
  #several branching options.
  #Aside from the number ID issues, the return statements in get_county and
  #get_precincts need to return only the info for a single county, but the
  #cache results store all counties' info together.
  def get_county(self, countyId, now_ish):
    return self.get_from_cache('counties',
                               now_ish)[self.id_to_COUNTY[countyId]]
  
  def get_precincts(self, countyId, now_ish):
    return self.get_from_cache('precincts',
                               now_ish)[self.id_to_COUNTY[countyId]]
  
  def get_state_results(self, now_ish):
    return self.get_from_cache('state', now_ish)
  
  def get_prec0(self, now_ish):
    return self.get_from_cache('precinct0', now_ish)
  
  def lights_out(self, now_ish):
    return False #simulator shuts off when the hard drive cache is done.

#Fetch data at the statewide level for the election of interest.
#If all precincts have reported and results are final, exit
def run():
  election_day = "20190514"
  nc09_counties = {
     4:'Anson',
     9:'Bladen',
    26:'Cumberland',
    60:'Mecklenburg',
    77:'Richmond',
    78:'Robeson',
    83:'Scotland',
    90:'Union'}
  repo = "./docs/2019/may/14/nc09/"
  cache_write = "./../cache/2019/may/14/"
  rep_names = {
    'Stevie Rivenbark Hull',
    'Matthew Ridenhour',
    'Stony Rushing',
    'Fern Shubert',
    'Albert Lee Wiley, Jr.',
    'Chris Anglin',
    'Dan Bishop',
    'Leigh Thomas Brown',
    'Kathie C. Day',
    'Gary Dunn'}
  
  AutoDown(
    election_day,
    {i:c.upper() for i,c in nc09_counties.items()},
    repo,
    cache_path=cache_write,
    filter=(lambda x : [a
                        for a in x
                        if a['bnm'] in rep_names])
    ).run()

def dry_run(sim_start=None):
  election_day = "20190430"
  
  nc03_counties = {
     7: 'Beaufort',
    15: 'Camden',
    16: 'Carteret',
    21: 'Chowan',
    25: 'Craven',
    27: 'Currituck',
    28: 'Dare',
    40: 'Greene',
    48: 'Hyde',
    52: 'Jones',
    54: 'Lenoir',
    67: 'Onslow',
    69: 'Pamlico',
    70: 'Pasquotank',
    72: 'Perquimans',
    74: 'Pitt',
    89: 'Tyrrell'}
  
  repo = "./docs/2019/apr/30/nc03/"
  cache_read = "./../cache/2019/apr/30/"
  
  default_sim_start = datetime.datetime(2019, 4, 30, 19, 30)
  id_to_COUNTY = {i:c.upper() for i,c in nc03_counties.items()}
  
  #start simulation from 7:30PM, when polls closed
  sim = FromCache(
    cache_read,
    sim_start or default_sim_start,
    id_to_COUNTY)
  
  AutoDown(
    election_day,
    id_to_COUNTY,
    repo,
    cache_path=None,
    simulator=sim
    ).run()
