import requests
import time
import datetime
import subprocess
import json
import os

def fill_blanks(cid=None):
  now = datetime.datetime.now()
  values = (now.year, now.month, now.day, now.hour, now.minute)
  return values if cid is None else tuple(cid) + values

def minute():
  return fill_blanks()[-1]

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

class AutoDown:
  
  def __init__(
      self,
      date_string,
      countyIDs,
      repo_path,
      cache_path='./cache/',
      simulator=None):
    
    if cache_path and simulator:
        raise Exception(("Simulating by reading a cache and then also writing "
                         "into that cache would be a bad idea."))
    #if cache_path is falsey, step-by-step results are not cached
    self.base_url = 'https://er.ncsbe.gov/enr/%s/data/' % date_string
    self.countyIDs = list(countyIDs)
    self.repo_path = repo_path[:-1] if repo_path.endswith('/') else repo_path
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
  
  def upload(self, state, county, prec):
    with open(self.repo_path + "/results_0.txt", 'w') as into:
        into.write(str(state))
    for County,json in county.items():
        with open(self.repo_path + "/results_%d.txt" % County,
                  'w') as into:
            into.write(str(json))
    for County,json in prec_dict.items():
        with open(self.repo_path + "/precinct_%d.txt" % County,
                  'w') as into:
            into.write(str(json))
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

  def run(self):
    prev_state_results = None
    
    while True:
      self.now_ish = fill_blanks()
      prev_minute = self.now_ish[-1]
      
      state_results = self.getter.get_state_results(self.now_ish)
      precincts = None
      if state_results != prev_state_results:
        prev_state_results = state_results
        
        counties = {county:self.getter.get_county(county, self.now_ish)
                    for county in self.countyIDs}
        precincts = {county:self.getter.get_precincts(county, self.now_ish)
                     for county in self.countyIDs}
        
        print("Change of state")
        self.cache_it("state",state_results)
        self.cache_it("counties",counties)
        self.cache_it("precincts",precincts)
        
        self.upload(state_results, counties, precincts)
        
      if results_are_final(state_results, precincts):
        print("All precincts reported. Done.")
        return
      
      for interval in intervals():
        m = minute()
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
  repo = "."
  cache_write = "./../cache/2019/may/14/"
  
  AutoDown(election_day, nc09_counties, repo, cache_write).run()

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
  
  repo = "."
  cache_read = "./../cache/2019/apr/30/"
  
  #start simulation from 7:29PM, before polls even closed
  sim = FromCache(cache_read, datetime.datetime(2019, 4, 30, 19, 29))
  
  AutoDown(election_day, nc03_counties, repo, cache=None, simulator=sim).run()
