#!/bin/bash
#Script to check if we should upgrade
# Read a flat file owned by www-data
# Command "upgrade=yes" should be placed in file
# This script will run in Cron, and check every 20 seconds
# Can also look for other commnands we may want to run.

#Implement in the database
# ID = Autoincrement
# date
# message
# status = new, processing, complete, error
# response = input any messgaes or results to return to queue requestor

#Get some common variables

source /home/HiveControl/scripts/hiveconfig.inc
source /home/HiveControl/scripts/data/logger.inc
DB=$HOMEDIR/data/hive-data.db

DATE=$(TZ=":$TIMEZONE" date '+%F %T')


#First get the command
cmd=$(sqlite3 $DB "SELECT message from msgqueue WHERE status='new' LIMIT 1";)
cmdid=$(sqlite3 $DB "SELECT id from msgqueue WHERE status='new' LIMIT 1";)

#Next sanitize for any stupid , should happen at the website, but you never know.
cmd=${cmd//[^a-zA-Z0-9_]/}

#Run through our case switch
case "$cmd" in
        upgrade)
            loglocal "$DATE" MSGQUEUE SUCCESS "Message Queue received upgrade command"
            #Set status to processing
            sqlite3 $DB "UPDATE msgqueue SET status='processing' WHERE id=$cmdid;"
            cd $HOMEDIR
            saveresult=$(/home/HiveControl/upgrade.sh)
            TEMPSAVE="/home/HiveControl/scripts/system/tempsave"
            echo $saveresult > $TEMPSAVE
            result=$(cat $TEMPSAVE |tail -c 8)
            #result=$(/home/HiveControl/scripts/system/foo.sh | tail -1)
            #Check to see if we ran
            if [[ "$result" == "success" ]]; then
            	sqlite3 $DB "UPDATE msgqueue SET response='Successfully Updated HiveControl', status='complete' WHERE id=$cmdid;"
            else
            	sqlite3 $DB "UPDATE msgqueue SET response='$saveresult', status='error' WHERE id=$cmdid;"
            fi
            ;;
        cleardata)
            loglocal "$DATE" MSGQUEUE SUCCESS "Message Queue received cleardata command"
            ;;            
        null)
            somecommand
            ;;
        *)
		#Not a valid command, so clear the queue
		#loglocal "$DATE" MSGQUEUE ERROR "Message Queue received an invalid command"
            exit 1
esac




