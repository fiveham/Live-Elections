/* This is for a Worker thread that checks once a minute for updated election results, 
   sends an update to the main thread if there's news, shuts itself down if the 
   results are final, or else just waits until the next minute to start the cycle over
   again. */

self.addEventListener('message', start, false);

function start(event){
  var prev_results = {'updated': ""};
  var summary_url = event.data;

  var minute = (new Date()).getMinutes();
  while(true){
    var fetch = new XMLHttpRequest();
    fetch.open("GET", summary_url+'?m='+minute, false);
    
    console.log("About to GET: "+minute);
    fetch.send(null);
    console.log("Just got: "+minute);
    
    var results = JSON.parse(fetch.responseText);
    
    if( results['updated'].valueOf() != prev_results['updated'].valueOf() ){
      //send results to main thread as an "update" message
      self.postMessage(results);
    }
    prev_results = results;
    
    if(results.isFinal){
      break; //leave the loop
    } else{
      //wait until next minute
      var test_minute;
      while(true){
        test_minute = (new Date()).getMinutes();
        if(test_minute != minute){
          minute = test_minute;
          break;
        } else{
          wait_5();
        }
      }
    }
  }
  //leave suicide note for main thread to find
  self.postMessage({'an_hero': true});
  //kill self
  self.close();
}

async function wait_5() {
  await sleep(5000);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
