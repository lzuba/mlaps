#!/bin/bash

while ! mycli mysql://dev:dev@db:3306/dev; do
    sleep 1
done

python3 app/starter.py -dev
