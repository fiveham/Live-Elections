import requests
import time
import datetime
import subprocess
import json
import os

def fill_blanks(cid=None):
  now = str(datetime.datetime.now())
  return ((now.day, now.hour, now.minute)
          if cid is None
          else (cid, now.day, now.hour, now.minute))

def minute():
  return fill_blanks()[-1]

def results_are_final(state_result_list, precinct_result_dict):
  sample = next(iter(state_result_list))
  return (sample['prt'] == sample['ptl'] and 
          all(all('final' in d['sta'].lower()
                  for d in v)
              for v in precinct_result_dict.values()))

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
  
  def cache_it(self, label, json):
    if not self.cache_path:
      return
    times = fill_blanks()
    content = tuple(label) + times
    with open(self.cache_path + '%s_%d-%d-%d.txt' % content, 'w') as into:
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
        ['git', 'commit', '-m', "upload %d-%d-%d results"%fill_blanks()],
        cwd=self.repo_path)
    subprocess.run(
        "git push origin master".split(),
        cwd=self.repo_path)
  
  #method for simulator
  def get_county(self, countyID):
    return requests.get(
        self.base_url + 'results_%d.txt?v=%d-%d-%d' % fill_blanks(countyID)
        ).json()
  
  #method for simulator
  def get_state_results(self):
    return self.get_county(0)
  
  #method for simulator
  def get_precincts(self, countyID):
    return requests.get(
        self.base_url + 'precinct_%d.txt?v=%d-%d-%d' % fill_blanks(countyID)
        ).json()
  
  def run(self):
    prev_state_results = None
    
    while True:
      prev_minute = minute()
      
      state_results = self.getter.get_state_results()
      precincts = None
      if state_results != prev_state_results:
        prev_state_results = state_results
        print("Change of state")
        self.cache_it("state",state_results)
        
        counties = {county:self.getter.get_county(county)
                    for county in self.countyIDs}
        self.cache_it("counties",counties)
        
        precincts = {county:self.getter.get_precincts(county)
                     for county in self.countyIDs}
        self.cache_it("precincts",precincts)
        
        self.upload(state_results, counties, precincts)
        
      if results_are_final(state_results, precincts):
        print("All precincts reported. Done.")
        return
      
      while minute() == prev_minute:
        time.sleep(10)
      print("Doing it again: "+minute())

class FromCache:
  def __init__(self, cache_dir, sim_start):
    self.cache_dir = cache_dir if cache_dir.endswith('/') else cache_dir+'/'
    
    #When this simulation starts, it will pretend that that moment is the
    #moment represented by sim_start
    self.sim_start = sim_start
    
    #The actual moment in time when this simulation begins running
    self.op_start = None 
    
    #TODO sort as datetime.datetime objects then convert to tuples
    self.cache_minutes = [
        tuple(int(n)
              for n in file[1+file.index('_'):file.index('.')].split('-'))
        for file in os.listdir(self.cache_dir[:-1])
        if any(file.startswith(x) and file.endswith('.txt')
               for x in ('state','counties','precincts'))]
  
  def date_time_tuple(self):
    now = datetime.datetime.now()
    diff = now - self.op_start
    then = str(self.sim_start + diff)
    return (then.day, then.hour, then.minute)
  
  def before(self, dhm):
      if dhm in self.cache_minutes:
        return dhm
      else:
        return next(iter(minute
                         for minute in reversed(self.cache_minutes)
                         if minute < dhm),
                    next(iter(self.cache_minutes)))
  
  def set_op_start(self):
    self.op_start = self.op_start or datetime.datetime.now()
  
  def get_county(self, countyID):
    self.set_op_start()
    ddt = self.date_time_tuple()
    cache_dhm = self.before(ddt)
    with open(
        self.cache_dir + "counties_%d-%d-%d.txt" % cache_dhm, 'r') as outof:
      return json.load(outof)[countyId]
  
  def get_state_results(self):
    self.set_op_start()
    ddt = self.date_time_tuple()
    cache_dhm = self.before(ddt)
    with open(self.cache_dir + 'state_%d-%d-%d.txt' % ddt, 'r') as outof:
      return json.load(outof)
  
  def get_precincts(self, countyID):
    self.set_op_start()
    ddt = self.date_time_tuple()
    cache_dhm = self.before(ddt)
    with open(self.cache_dir + "precincts_%d-%d-%d.txt" % ddt, 'r') as outof:
      return json.load(outof)[countyId]

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
