# olo_chatgpt
Experimental Chat GPT Scraper


Install the camoufox package first: pip install -U camoufox[geoip]

When you are running for the first time, just keep one question and one parallel worker. It will automatically download other necessary files. 

To run this test, you can just set up the questions in the questions list and setup the number of parallel workers that you want to run. 
After the script executes completely, a result json file will get created in the same directory. 

You can also turn off the headless mode in the line 147. 


Have also added the method which can automatically calculate the number of optimal workers required to finish the job in the target time. Not using it for now. 

Lot of improvements can be made in this script. 
