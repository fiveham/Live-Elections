# Live-Elections
This is where live election result updates from the NCSBE (and any other similar sources) will be uploaded to get around a lack of CORS so that maps in Elections can update live.

# What and How
`auto_down.py`, run on my PC, will download (and cache) election results from the North Carolina State Board of Elections minute by 
minute. It then saves the most recent version of the results as well as a summary file to a local git repo and pushes the changes to 
the remote here.  Once the results and summary are uploaded here, a live-updating map can `get` that information. Trying to `get` it 
directly from the NCSBE site fails for CORS reasons.


