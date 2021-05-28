#! /bin/sh

cd ~/smarthome
touch nohup.out
rm nohup.out
nohup python3 -u smarthome.py &
sleep 2
tail -f nohup.out