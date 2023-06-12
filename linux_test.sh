#!/usr/bin/env bash
# might be out of date
# Used for testing in CD/CI
# Adjustments made here are for linux cmd since macos has different implemenations sometimes (see openssl)

# Settings
set -ex # commented out for now because exiting on every error seems harsh

# Constants
SUPPORT="/tmp/Support"
MLAPS_ENDPOINT="https://mlaps.$YOURCOMPANY.com/api"                                    # MLAPS HOST
MLAPS_CA="com.$YOURCOMPANY.mlaps"                                             # MLAPS_CA
CA_FILE="$SUPPORT/mlaps-ca.pem"        # Path to CA file  *TODO* write CA to each host with jamf
PW_FILE="$SUPPORT/mlaps-password"      # Path to Password File
EXP_FILE="$SUPPORT/mlaps-expiration"   # Path to Expiry File
CSR_FILE="$SUPPORT/mlaps-csr"          # Path to CSR
CRT_FILE="$SUPPORT/mlaps-crt"          # Path to CRT
KEY_FILE="$SUPPORT/mlaps-key"          # Path to KEY
UPDATE_ID_FILE="$SUPPORT/mlaps-updateid"                            # Path to KEY
LOG_FILE="$LOGGINGFILE"                                            # Path to logfile
SN="Test-Serial-Number"   # Serial number
HN=$(hostname)                                                           # Hostname
SUBJ="/C=$CERT_COUNTRY/O=LAPS/OU=${SN}"
CURLOPTION=(-k)

# Settings
CURL_N_RETRIES=5                                                        #the number of times curl will try again
CURL_MAX_T=10                                                           # the time curl will wait for the response before trying again
CURL_DELAY=0                                                            #some setting to tweak
CURL_MAX_RETRY_TIME=60                                                  #how long it takes for curl to give up
N_RETRIES=4
T_RETRIES=3

# Templates
JSON_ENROLLMENT_FORMAT='{"csr":"%s", "sn":"%s", "hn":"%s"}\n'           # Format for json enrollment payload
JSON_PASS_RESPONSE_FORMAT='{"Success_Status":"%s", "Password":"%s", "Expiry_Date":"%s", "updateSessionID":"%s"}\n'     # Format for json password response payload

#Runtime Data
UPDATEID=""


mkdir -p "$SUPPORT"

function cleantmp(){
  rm -f "$PW_FILE" "$EXP_FILE"
}


# format and write a line into /var/log/jamflog
function jamflog(){
  local MSG=""
  MSG+=$(date -u "+%a %b %d %H:%M:%S ")
  MSG+="$HN"
  MSG+=" LAPS[$$]: "
  MSG+="$@"
  echo "$MSG" 
}

function errlog(){
  if [ -z "$1" ]; then
    jamflog "ERR: $@"
  else
    jamflog "ERR: (line $(caller)) There has been an error"
  fi
}

# trap \
#        "{ /usr/bin/rm -f ${PW_FILE} ${EXP_FILE} ; exit 1 ; }" \
#        SIGINT SIGTERM ERR EXIT

function enroll(){
  jamflog "Generating CSR & KEY"

  local CSR=$(openssl req   \
    -new              \
    -nodes             \
    -newkey rsa:2048    \
    -keyout "$KEY_FILE"    \
    -subj   "$SUBJ" | tee "$CSR_FILE" | base64 -w0 - ; exit ${PIPESTATUS[0]})

  if [ $? ]; then
    jamflog "Generated CSR for enrollment!"
  else
    errlog "Failed to generate CSR for enrollment"
    cleanEnrollment
    return 1
  fi

  local PAYLOAD="{\"csr\":\"$CSR\", \"sn\":\"$SN\", \"hn\":\"$HN\"}"

  (curl                             \
    "${CURLOPTION[@]}"               \
    --request POST                    \
    --url "$MLAPS_ENDPOINT/enroll"     \
    --retry $CURL_N_RETRIES             \
    --max-time $CURL_MAX_T               \
    --retry-delay $CURL_DELAY             \
    --retry-max-time $CURL_MAX_RETRY_TIME  \
    -H 'Content-Type: application/json'     \
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
    "${CURLOPTION[@]}"              \
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
  echo "$UPDATEID" > "$UPDATE_ID_FILE"
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
  fi
}

function send_pw(){

  #$(printf "$" "$1" "$2" "$UPDATEID") 
  local PAYLOAD="{\"Success_Status\":\"$1\", \"Password\":\"$2\", \"updateSessionID\":\"$UPDATEID\"}"

  local PW_DATA=$(curl             \
    "${CURLOPTION[@]}"              \
    --request POST                   \
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
    jamflog "Server recieved admin Password payload"
    return 0
  else
    errlog "Could not transmit admin Password payload"
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
    "${CURLOPTION[@]}"              \
    --request POST                   \
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
    send_pw 1 "Failed to generate new pw: $newpw"; errlog "Failed to generate new pw: $newpw"; return 10; 
   fi

   # inform server about new pw to be set
   if ! local first_resp=$(send_pw 0 "$newpw"); then 
    errlog "Failed to send first password payload to server"; return 12; 
   fi
   
   # actually setting new pw
   local res1="Goodbye";
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
  #check/wait for a internet connection
  while ! ping -c1 -W1 1.1.1.1 &> /dev/null ; do
    sleep 1
  done

  shlock -f $PID_FILE -p $$ || cleanupPid
  
  if [ -s "$UPDATE_ID_FILE" ]; then
    jamflog "Found remaining updatesession id..."
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
    local res=$("$@");echo $? && echo $res;break || {
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

sleep 5

enroll

checkin

checkin
