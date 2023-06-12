MLAPS_DIR="somePathToTheMlapsRootPath"
[[ -d "$MLAPS_DIR/bin" ]] || virtualenv $MLAPS_DIR
source $MLAPS_DIR/bin/activate
python3 -m pip \
    install -r $MLAPS_DIR/requirements.txt
