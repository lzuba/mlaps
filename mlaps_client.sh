#!/usr/bin/env bash

# Settings
#set -ex # commented out for now because exiting on every error seems harsh
export PATH="/usr/local/bin/:/usr/local/sbin/:/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

# Constants
SUPPORT="$SUPPORTPATH"
ADMIN_USER_NAME="admin"
ADMIN_USER_HOME="/Users/$ADMIN_USER_NAME"
MLAPS_HOSTNAME="https://mlaps.$YOURCOMPANY.com"                     # MLAPS HOST
MLAPS_ENDPOINT="$MLAPS_HOSTNAME/api"                                # MLAPS API
MLAPS_CA="com.$YOURCOMPANY.mlaps"                                   # MLAPS_CA
CA_FILE="$SUPPORT/mlaps-ca.pem"                                     # Path to CA file
PW_FILE="$SUPPORT/mlaps-password"                                   # Path to Backup Password File
CSR_FILE="$SUPPORT/mlaps-csr"                                       # Path to CSR
CRT_FILE="$SUPPORT/mlaps-crt"                                       # Path to CRT
KEY_FILE="$SUPPORT/mlaps-key"                                       # Path to KEY
UPDATE_ID_FILE="$SUPPORT/mlaps-updateid"                            # Path to KEY
LOG_FILE="$LOGGINGFILE"                                             # Path to logfile
SN=$(system_profiler SPHardwareDataType | awk '/Serial/{ print $4 } ')  # Serial number
HN=$(hostname)                                                          # Hostname
SUBJ="/C=$CERT_COUNTRY/O=LAPS/OU=${SN}"                                 # CSR Subject
PID_FILE="/var/run/mlaps.pid"                                           # Path to the pid file

# Settings
CURL_N_RETRIES=5                                                        # the number of times curl will try again
CURL_MAX_T=10                                                           # the time curl will wait for the response before trying again
CURL_DELAY=0                                                            # some setting to tweak
CURL_MAX_RETRY_TIME=60                                                  # how long it takes for curl to give up
N_RETRIES=4
T_RETRIES=3

# Templates
#JSON_ENROLLMENT_FORMAT='{"csr":"%c", "sn":"%s", "hn":"%h"}'           # Format for json enrollment payload
#JSON_PASS_RESPONSE_FORMAT='{"Success_Status":"%s", "Password":"%p", "updateSessionID":"%i"}'     # Format for json password response payload
#JSON_PASS_UPDATE_FORMAT='{"res":"$r", "updateSessionID":"%i"}'
#JSON_PASS_CHECKIN_FORMAT='{"sn":"%s", "hn":"%h"}'

#Runtime Data
UPDATEID=""

#Security
BASIC_AUTH="username:password"

function panic(){
  # rm pidfile
  cleanupPid
  errlog "Unexpected exit!: (line $(caller))"
  exit 255
}

# cleanup pidfile if process is not running anymore
function cleanupPid(){
  if [ -f $PID_FILE ]; then
    PID=$(cat $PID_FILE)
    ps -p $PID > /dev/null 2>&1
    if [ $? -eq 0 ]; then
      echo "Process already running"
      exit 1
    else
      ## Process not found assume not running
      echo $$ > $PID_FILE
      if [ $? -ne 0 ]; then
        echo "Could not create PID file"
        exit 1
      fi
    fi
  else
    echo $$ > $PID_FILE
    if [ $? -ne 0 ]; then
      echo "Could not create PID file"
      exit 1
    fi
  fi
}

function cleanEnrollment(){
  shred "$CSR_FILE" "$CRT_FILE" "$KEY_FILE"
  rm -f "$CSR_FILE" "$CRT_FILE" "$KEY_FILE"
}


# format and write a line into /var/log/jamflog
function jamflog(){
  local MSG=""
  MSG+=$(date -u "+%a %b %d %H:%M:%S ")
  MSG+="$HN"
  MSG+=" LAPS[$$]: "
  MSG+="$@"
  echo "$MSG" >> "$LOG_FILE"
}

function errlog(){
  if [ -z "$1" ]; then
    jamflog "ERR: (line $(caller)) There has been an error"
  else
    jamflog "ERR: $@"
  fi
}

# trap \
#        "{ /usr/bin/rm -f ${PW_FILE} ${EXP_FILE} ; exit 1 ; }" \
#        SIGINT SIGTERM ERR EXIT

# SIGEMT SIGINFO
trap 'panic' \
  SIGHUP SIGINT SIGQUIT SIGILL SIGTRAP SIGABRT SIGFPE \
  SIGKILL SIGBUS SIGSEGV SIGSYS SIGPIPE SIGALRM SIGTERM SIGURG \
  SIGSTOP SIGTSTP SIGCONT SIGTTIN SIGTTOU SIGIO SIGXCPU \
  SIGXFSZ SIGVTALRM SIGPROF SIGWINCH SIGUSR1 SIGUSR2
trap 'errlog' ERR                                                     # Traps errors that aren't handled and logs them without exiting

# create pid file ($pid > file)
# exit if exists
# shlock -f $PID_FILE -p $$ || cleanupPid

#Function to generate csr and send to /enroll
function enroll(){
  jamflog "Generating CSR & KEY"

  local CSR=$(openssl req   \
    -new              \
    -nodes             \
    -newkey rsa:2048    \
    -keyout "$KEY_FILE"    \
    -subj   "$SUBJ" | tee "$CSR_FILE" | openssl base64 -e ; exit ${PIPESTATUS[0]})

  if [ $? ]; then
    jamflog "Generated CSR for enrollment!"
  else
    errlog "Failed to generate CSR for enrollment"
    cleanEnrollment
    return 1
  fi

  local PAYLOAD="{\"csr\":\"$CSR\", \"sn\":\"$SN\", \"hn\":\"$HN\"}"

  local extra_options=()
  if [[ test -n $BASIC_AUTH ]]; then
    extra_options+=(-u "$BASIC_AUTH")
  fi

  (curl                             \
    --cacert "$CA_FILE"              \
    --request POST                    \
    --url "$MLAPS_ENDPOINT/enroll"     \
    --retry $CURL_N_RETRIES             \
    --max-time $CURL_MAX_T               \
    --retry-delay $CURL_DELAY             \
    --retry-max-time $CURL_MAX_RETRY_TIME  \
    -H 'Content-Type: application/json'     \
    "${extraArgs[@]}"                        \
    --data "$PAYLOAD" | jq -r '.response' | tee "$CRT_FILE";  exit ${PIPESTATUS[0]} ;)

  if [ $? ]; then
    jamflog "Downloaded cert"
    local crt_hash=$(openssl md5 <(openssl x509 -noout -modulus -in "$CRT_FILE"))
    local key_hash=$(openssl md5 <(openssl  rsa -noout -modulus -in "$KEY_FILE"))
    if [ "$crt_hash" == "$key_hash" ]; then
      jamflog "certificate has been downloaded without error"
      return 0
    else
      errlog "certificate downloaded with errors, cleaning up broken files"
      #cleanEnrollment
      return 1
    fi
  else
    jamflog "Failed to download cert, cleaning up broken files"
    #cleanEnrollment
    return 1
  fi
}

#Function which will make a request to /checkin to find out whether to update pw
function checkin(){

  local PAYLOAD="{\"sn\":\"$SN\", \"hn\":\"$HN\"}"

  local CHECKIN_DATA=$(curl        \
    --cacert "$CA_FILE"             \
    --request POST                   \
    --cert "$CRT_FILE"                \
    --key  "$KEY_FILE"                 \
    --data "$PAYLOAD"                   \
    --url "$MLAPS_ENDPOINT/checkin"     \
    --retry $CURL_N_RETRIES              \
    --max-time $CURL_MAX_T                \
    --retry-delay $CURL_DELAY              \
    --retry-max-time $CURL_MAX_RETRY_TIME   \
    --header 'Content-Type: application/json')



  local RESPONSE=$(echo "$CHECKIN_DATA")
  local STATUS=$(echo "$RESPONSE" | jq '.response')
  UPDATEID=$(echo "$RESPONSE" | jq -r '.updateSessionID')
  if [ "$UPDATEID" != "null" ] && [ -n "$UPDATEID" ]; then
    echo "$UPDATEID" > "$UPDATE_ID_FILE"
  fi
  #if [ -z "$UPDATEID" ]; then
  # echo "$UPDATEID" > "$UPDATE_ID_FILE"
  #fi

  if [ "$STATUS"  == "\"ok\""  ]; then
    jamflog "Password is still current -> nothing to do"
    return 0
  elif [ "$STATUS" == "\"update\"" ]; then
    jamflog "Updating Password..."
    retry "$N_RETRIES" "$T_RETRIES" set_pw && return 0 || return 99
  else
    errlog "Could not read server response"
    errlog "$RESPONSE"
  fi
}

function send_pw(){

  #$(printf "$" "$1" "$2" "$UPDATEID")
  local PAYLOAD="{\"Success_Status\":\"$1\", \"Password\":\"$2\", \"updateSessionID\":\"$UPDATEID\"}"

  local PW_DATA=$(curl             \
    --request POST                  \
    --cacert "$CA_FILE"              \
    --cert "$CRT_FILE"                \
    --key "$KEY_FILE"                  \
    --data "$PAYLOAD"                   \
    --url "$MLAPS_ENDPOINT/password"     \
    --retry $CURL_N_RETRIES               \
    --max-time $CURL_MAX_T                 \
    --retry-delay $CURL_DELAY               \
    --retry-max-time $CURL_MAX_RETRY_TIME    \
    --header 'Content-Type: application/json')

  local RESPONSE=$(echo "$PW_DATA" | jq -rc '.response')

  if [ "$RESPONSE" == "ok" ] ; then
    jamflog "Server received first admin Password payload"
    return 0
  elif [ "$RESPONSE" == "Password not expired" ] ; then
    jamflog "Server reported that Password is not expired, aborting setting new password and cleaning up updateid"
    rm "$UPDATE_ID_FILE"
    exit 5
  else
    errlog "Could not transmit admin Password payload"
    errlog "$RESPONSE"
    return 1
  fi
}

function gen_passwd(){
  local succ=0
  local pw=""
  while [ $succ -eq 0 ]
  do
    pw=$(LC_ALL=C tr -dc A-Za-z0-9_ < /dev/urandom | head -c 16 | xargs)
    #pw='jogb4GmFroee__MDh'
    #check if pw has a selected special character
    if [[ $pw =~ ['!@#$%^&*()_+'] ]]; then
      #check if pw has a number
      if [[ $pw =~ [0-9] ]]; then
        succ=1
        #lastly check if pw has 2 identical characters next to each other
        local prev="${pw:0:1}"
        for i in $(seq 2 ${#pw});do
          local cur=${pw:((i-1)):1}
          if [ "$prev" == $cur ]; then
            #echo "found duplicate"
            succ=0
          fi
          prev=$cur
        done
      else
        # one condition not met, rerun loop
        succ=0
      fi
    else
      # one condition not met, rerun loop
      succ=0
    fi
  done
  echo $pw
  #echo $(openssl rand -base64 10 | tr -d OoIi1lLS | head -c12;echo)
}

function send_pw_res(){
  jamflog $1
  local PAYLOAD="{\"res\":\"$1\", \"updateSessionID\":\"$UPDATEID\"}"
  local PW_DATA=$(curl             \
    --request POST                  \
    --cacert "$CA_FILE"              \
    --cert "$CRT_FILE"                \
    --key "$KEY_FILE"                  \
    --data "$PAYLOAD"                   \
    --url "$MLAPS_ENDPOINT/password-confirm"\
    --retry $CURL_N_RETRIES               \
    --max-time $CURL_MAX_T                 \
    --retry-delay $CURL_DELAY               \
    --retry-max-time $CURL_MAX_RETRY_TIME    \
    --header 'Content-Type: application/json')

  if [ $? -ne 0 ]; then
    errlog "Failed to send confirmation to server"
  fi

}

# wip
function set_pw(){
  # generate new pw
  if ! local newpw=$(gen_passwd); then
    send_pw 1 "Failed to generate new pw: $newpw"
    errlog "Failed to generate new pw: $newpw"
    return 10
  fi

   # inform server about new pw to be set
   send_pw 0 "$newpw"
   if [[ $? -eq 1 ]]; then
     errlog "Failed to send first password payload to server"
     return 12
   fi

   local res1=$(echo "-passwd /Users/admin $newpw " | dscl . );
   if [ "$res1" = "Goodbye" ]; then
     jamflog "Password Change successful, send confirmation"
     #read -p "Press enter to continue"
     send_pw_res "Success"
     #delete updatesessionid to persist the successful pw change
     rm "$UPDATE_ID_FILE"
     return 0
   else
     send_pw_res "Failed to set new pw: $res1"
     return 13
   fi
 }

 function main(){
   for var in "$@"
   do
       if [ "$var" == "-v" ]; then
         set -x
       fi
   done

   #check/wait for a internet connection
   while ! curl --cacert "$CA_FILE" -Is $MLAPS_HOSTNAME &> /dev/null ; do
     sleep 1
   done

   shlock -f $PID_FILE -p $$ || cleanupPid

   if [ -s "$UPDATE_ID_FILE" ]; then
     jamflog "Found valid updatesession id..."
     UPDATEID="$(<"$UPDATE_ID_FILE")"
     set_pw
   else
     if [ -e "$CRT_FILE" ];then
       checkin
     else
       enroll && checkin || errlog "Failed to enroll"
     fi
   fi
   rm $PID_FILE
 }

 function retry {
   local max=$1 ; shift
   local delay=$1 ; shift
   local n=1

   jamflog "Trying to run \"$@\""

   while true; do
     "$@" && break || {
       if [[ $n -lt $max ]]; then
         ((n++))
         errlog "Failed to run \"$@\": attempt $n/$max:"
         sleep $delay;
       else
         errlog "\"$@\" has failed after $n attempts."
         return 1
       fi
     }
   done
 }


# for testing...(works like if __name__==main in python
[[ "${#BASH_SOURCE[@]}" -eq 1 ]] \
  && retry "$N_RETRIES" "$T_RETRIES" main $@ \
  || { echo "Happy testing!" ; }
