/*===================================================================================
  This is for a Worker thread that checks once a minute for updated election results, 
  sends an update to the main thread if there's news, shuts itself down if the 
  results are final, or else just waits until the next minute to start the cycle over
  again. 
  =================================================================================*/

var summary_url = null;
var prev_results = {'updated': ""};
var looperator = null;

self.addEventListener('message', start, false);

function start(event){
  summary_url = event.data;
  cycle();
  looperator = setInterval(cycle, 60000);
}

function cycle(){
  var time = new Date();
  var minute = time.getMinutes();
  var second = time.getSeconds();
  
  //fetch
  var fetch = new XMLHttpRequest();
  fetch.open("GET", summary_url+'?m='+minute+'&s='+second, false);
  fetch.send(null);
  var results = JSON.parse(fetch.responseText);
  
  //check if diff't --> msg to main thread
  if( results['updated'].valueOf() != prev_results['updated'].valueOf() ){
    self.postMessage(results);
    prev_results = results;
  }
  
  //check if final --> msg to main thread, kill self, quit looping
  if(results.isFinal){
    self.postMessage({'an_hero': true});
    self.close();
    clearInterval(looperator);
  }
  
  //wait till next minute
}
