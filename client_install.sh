#!/usr/bin/env bash
#set -ex
export PATH="/usr/bin:/usr/sbin:/usr/local/bin/:/usr/local/sbin/:/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
UNAME_MACHINE="$(uname -m)"
if [[ "$UNAME_MACHINE" == "arm64" ]]; then
    # M1/arm64 machines
    MPATH="/opt/$YOURCOMPANY/mlaps_client.sh"
    FPATH="/opt/$YOURCOMPANY/"
else
    # Intel machines
    MPATH="/usr/local/$YOURCOMPANY/mlaps_client.sh"
    FPATH="/usr/local/$YOURCOMPANY/"
fi
mkdir -p $FPATH
touch $MPATH
mkdir -p "/var/root/Library/Application Support/"
touch LOGGINGFILE

NAME="com.$YOURCOMPANY.mlaps"
PLIST_PATH="/Library/LaunchDaemons/$NAME.plist"
RANDOM_DELAY=$[ $RANDOM % 15 - 0 ]
RANDOM_DELAY=$[ $RANDOM_DELAY + 20 ] 

cat << EOF > $PLIST_PATH
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>$NAME</string>
    <key>Program</key>
    <string>$MPATH</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>$RANDOM_DELAY</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>13</integer>
            <key>Minute</key>
            <integer>$RANDOM_DELAY</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>16</integer>
            <key>Minute</key>
            <integer>$RANDOM_DELAY</integer>
        </dict>
    </array>
  </dict>
</plist>
EOF

curl -f $DOWNLOADURL | tee $MPATH

brew install jq
brew install coreutils

chmod +x $MPATH
launchctl bootstrap system $PLIST_PATH

