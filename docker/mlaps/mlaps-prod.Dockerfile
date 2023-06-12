FROM $PATHTOWHEREYOURDOCKERIMAGELIVES

COPY secrets.ini /mlaps/app
COPY secrets.json /mlaps/app

WORKDIR /mlaps

RUN ln -sf /proc/1/fd/1 /mlaps/logs/log.log

ENTRYPOINT [ "python", "app/starter.py" ]
