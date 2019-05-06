import requests
import time
import datetime
import subprocess
import json
import os

def now_tuple():
  now = datetime.datetime.now()
  return (now.year, now.month, now.day, now.hour, now.minute)

def results_are_final(state_result_list, precinct_result_dict):
  sample = next(iter(state_result_list))
  return (sample['prt'] == sample['ptl'] and 
          all(all('final' in d['sta'].lower()
                  for d in v)
              for v in precinct_result_dict.values()))

def intervals():
  for x in (10,8,6,4):
    yield x
    yield x
  while True:
    yield 2

def top1(list, pty):
  top = max(list, key=(lambda d : (d['vct']
                                    if d['pty'] == pty
                                    else -1)))
  return top['bnm']

def top2(list, pty):
  top = top1(list,pty)
  sec = max(list, key=(lambda d : (d['vct']
                                    if d['bnm'] != top and d['pty'] == pty
                                    else -1)))
  return [top,sec['bnm']]

def abstrindex(pty, tops, name):
  try:
    return tops[pty[0]].index(name)
  except ValueError: #name not in list
    return 2

def is_unreported(list): #varies between cty and pct results
  try: #only precinct results have 'sta'
    return all(d['sta'] == 'Not Reported' for d in list)
  except KeyError: #but county results have 'prt'
    return all(d['prt'] == '0' for d in list) #XXX not sure of type of d['prt']

def get_tops(list, tops):
  if is_unreported(list):
    return {"D": -1, "L": -1, "R": -1}
  else:
    return {pty[0]:abstrindex(pty,tops,top1(list,pty))
            for pty in ("DEM",'LIB','REP')}

def partition_by_precinct(county_results_by_precinct, tops):
  result = {d['aid']:[] for d in county_results_by_precinct}
  for d in county_results_by_precinct:
    precinct_name = d['aid']
    result[precinct_name].append(d)
  
  for precinct_name in result:
    prec_el_results = result[precinct_name]
    g = get_tops(prec_el_results, tops)
    d = {'top': g}
    result[precinct_name] = d
  return result

class AutoDown:
  
  def __init__(
      self,
      date_string,
      countyIDs,
      repo_path,
      translator=(lambda cId : cId),
      cache_path='./cache/',
      simulator=None):
    
    if cache_path and simulator:
      raise Exception(("Simulating by reading a cache and then also writing "
                       "into that cache would be a bad idea."))
    #if cache_path is falsey, step-by-step results are not cached
    self.base_url = 'https://er.ncsbe.gov/enr/%s/data/' % date_string
    self.countyIDs = list(countyIDs)
    self.repo_path = repo_path[:-1] if repo_path.endswith('/') else repo_path
    self.translator = translator
    self.cache_path = ((cache_path + '/') 
                       if cache_path and not cache_path.endswith('/') 
                       else cache_path)
    self.getter = simulator or self
    self.now_ish = None
  
  
  def cache_it(self, label, json):
    if not self.cache_path:
      return
    content = tuple(label) + self.now_ish
    with open(self.cache_path +
              '%s_%d-%d-%d-%d-%d.txt' % content, 'w') as into:
      into.write(str(json)+'\n')

  def distill_results(self, state, county, prec, finality):
    tops = {
      'D': top2(state, 'DEM'),
      'L': top2(state, 'LIB'),
      'R': top2(state, 'REP')
    }

    distilled = {
      'updated': "-".join(self.now_ish),
      'isFinal': finality or "",
      'top': tops,
      'by_county': {
        self.translator(cId): {
          'top': get_tops(county[cId], tops),
          'by_precinct': partition_by_precinct(prec[cId], tops),
        }
        for cId in county
      }
    }
    
    return distilled
  
  def upload(self, state, county, prec, finality):
    with open(self.repo_path + "/results_0.txt", 'w') as into:
      json.dump(state, into)

    for source,term in [[county, 'results'],
                        [prec,   'precinct']]:
      for cId,j in source.items():
        with open(self.repo_path + "/%s_%d.txt" % (term,cId), 'w') as into:
          json.dump(j, into)
    
    distilled = self.distill_results(state, county, prec, finality)
    with open(self.repo_path + "/summary.txt", 'w') as into:
      json.dump(distilled, into)
    
    subprocess.run("git add .".split(),
                   cwd=self.repo_path)
    subprocess.run(
        ['git',
         'commit',
         '-m',
         "upload %d-%d-%d-%d-%d results" % self.now_ish],
        cwd=self.repo_path)
    subprocess.run(
        "git push origin master".split(),
        cwd=self.repo_path)

  def fetch(self, label, countyID, now_ish):
    y,l,d,h,m = now_ish
    return requests.get(
        self.base_url + label + '_%d.txt?v=%d-%d-%d' % (countyID,d,h,m)
        ).json()
  
  #method for simulator
  def get_county(self, countyID, now_ish):
    return self.fetch('results', countyID, now_ish)
  
  #method for simulator
  def get_state_results(self, now_ish):
    return self.get_county(0, now_ish)
  
  #method for simulator
  def get_precincts(self, countyID, now_ish):
    return self.fetch('precinct', countyID, now_ish)

  #TODO make this thing shut off after midnight because that's too long
  def run(self):
    prev_state_results = None
    
    while True:
      right_now_ish = now_tuple())
      prev_minute = right_now_ish[-1]
      
      state_results = self.getter.get_state_results(right_now_ish)
      precincts = None
      finality = None
      if state_results != prev_state_results:
        prev_state_results = state_results
        self.now_ish = right_now_ish
        
        counties = {county:self.getter.get_county(county, self.now_ish)
                    for county in self.countyIDs}
        precincts = {county:self.getter.get_precincts(county, self.now_ish)
                     for county in self.countyIDs}
        
        print("Change of state")
        self.cache_it("state",state_results)
        self.cache_it("counties", {self.translator(cId):stuff
                                   for cId,stuff in counties.items()})
        self.cache_it("precincts", {self.translator(cId):stuff
                                   for cId,stuff in precincts.items()})

        finality = results_are_final(state_results, precincts)
        self.upload(state_results, counties, precincts, finality)

      finality = (finality
                  if finality is not None
                  else results_are_final(state_results, precincts))
      if finality:
        print("All precincts reported. Done.")
        return
      
      for interval in intervals():
        m = now_tuple()[-1]
        if m != prev_minute:
          print("Doing it again: " + m)
          break
        time.sleep(interval)

class FromCache:
  def __init__(self, cache_dir, sim_start):
    self.cache_dir = cache_dir if cache_dir.endswith('/') else cache_dir+'/'
    
    #When this simulation starts, it will pretend that that moment is the
    #moment represented by sim_start
    self.sim_start = sim_start
    
    #The actual moment in time when this simulation begins running
    self.op_start = None 
    
    self.cache_minutes = {
        label:sorted(tuple(int(n)
                           for n in file[1+file.index('_'):-4].split('-'))
                     for file in os.listdir(self.cache_dir)
                     if file.startswith(label))
        for label in ('state','counties','precincts')}
  
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
                  next(iter(self.cache_minutes[label])))
  
  def set_op_start(self, now_ish):
    self.op_start = self.op_start or datetime.datetime( *now_ish )
  
  def get_from_cache(self, label, now_ish):
    self.set_op_start(now_ish)
    simmom = self.simulation_moment(now_ish)
    cache_moment = self.before(label, simmom)
    with open(
        self.cache_dir + label + "_%d-%d-%d-%d-%d.txt" % cache_moment,
        'r') as outof:
      return json.load(outof)
  
  def get_county(self, countyID, now_ish):
    return self.get_from_cache('counties', now_ish)[countyId]
  
  def get_state_results(self, now_ish):
    return self.get_from_cache('state', now_ish)
  
  def get_precincts(self, countyID, now_ish):
    return self.get_from_cache('precincts', now_ish)[countyId]

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
  
  AutoDown(
    election_day,
    nc09_counties,
    repo,
    translator=(lambda cId: nc09_counties[cId]),
    cache=cache_write
    ).run()

def dry_run():
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
  
  #start simulation from 7:29PM, before polls even closed
  sim = FromCache(cache_read, datetime.datetime(2019, 4, 30, 19, 29))
  
  AutoDown(
    election_day,
    nc03_counties,
    repo,
    translator=(lambda cId: nc03_counties[cId]),
    cache=None,
    simulator=sim
    ).run()
