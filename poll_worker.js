/* This is for a Worker thread that checks once a minute for updated election results, 
   sends an update to the main thread if there's news, shuts itself down if the 
   results are final, or else just waits until the next minute to start the cycle over
   again. */

var prev_results = null;
var summary_url = "https://fiveham.github.io/Live-Elections/2019/apr/30/nc03/summary.txt?m=";

var minute = (new Date()).getMinutes();
while(true){
  var fetch = new XMLHttpRequest();
  fetch.open("GET", summary_url+minute, false);
  fetch.send(null);
  var results = JSON.parse(fetch.responseText);
  
  if(results != prev_results){
    //TODO send fetch.responseText to main thread as an "update" message
    
  }
  prev_results = results;
  
  if(is_final(results)){
    //TODO leave suicide note for main thread to find
    
    //kill self
    self.close();
  }
  
  //wait until next minute
  var test_minute;
  while(true){
    test_minute = (new Date()).getMinutes();
    if(test_minute != minute){
      minute = test_minute;
      break;
    } else{
      //TODO wait 5 seconds
      
    }
  }
}

function is_final(results){
  //TODO
  return true;
}
