#!/usr/bin/env bash

# Settings
set -ex # commented out for now because exiting on every error seems harsh
export PATH="/usr/local/bin/:/usr/local/sbin/:/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

# Constants
SUPPORT="$SUPPORTPATH"
MLAPS_ENDPOINT="https://mlaps.$YOURCOMPANY.com/api"                           # MLAPS HOST
CSR_FILE="$SUPPORT/mlaps-csr"                                       # Path to CSR
CRT_FILE="$SUPPORT/mlaps-crt"                                       # Path to CRT
KEY_FILE="$SUPPORT/mlaps-key"                                       # Path to KEY
LOG_FILE="$LOGGINGFILE"                                            # Path to logfile
SN=$(system_profiler SPHardwareDataType | awk '/Serial/{ print $4 } ')  # Serial number
HN=$(hostname)                                                          # Hostname
SUBJ="/C=$CERT_COUNTRY/O=LAPS/OU=${SN}"                                            # CSR Subject
PID_FILE="/var/run/mlaps.pid"                                           # Path to the pid file

# Settings
CURL_N_RETRIES=5                                                        # the number of times curl will try again
CURL_MAX_T=10                                                           # the time curl will wait for the response before trying again
CURL_DELAY=0                                                            # some setting to tweak
CURL_MAX_RETRY_TIME=60                                                  # how long it takes for curl to give up
N_RETRIES=4
T_RETRIES=3



function panic(){
  # rm pidfile
  cleanupPid
  errlog "Unexpected exit!: (line $(caller))"
  exit 255
}

# cleanup pidfile if process is not running anymore
function cleanupPid(){
  pid=$(cat $PID_FILE)
  if test -n $pid && ! ps -p $pid ; then
    rm $PID_FILE
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
  SIGSTOP SIGTSTP SIGCONT SIGCHLD SIGTTIN SIGTTOU SIGIO SIGXCPU \
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
    -subj   "$SUBJ" | tee "$CSR_FILE" | base64 -i - ; exit ${PIPESTATUS[0]})

  if [ $? ]; then
    jamflog "Generated CSR for enrollment!"
  else
    errlog "Failed to generate CSR for enrollment"
    cleanEnrollment
    return 1
  fi

  local PAYLOAD="{\"csr\":\"$CSR\", \"sn\":\"$SN\", \"hn\":\"$HN\"}"

  (curl          -k                   \
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

[[ "${#BASH_SOURCE[@]}" -eq 1 ]] && enroll