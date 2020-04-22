#!/usr/bin/env bash

# Eventing: Portugal-Spain
python3 run.py -m 7576 -t Portugal -s eventing -k pass_value
python3 run.py -m 7576 -t Spain -s eventing -k pass_value

python3 run.py -m 7576 -t Portugal -s eventing -k basic
python3 run.py -m 7576 -t Spain -s eventing -k basic


# Eventing: World Cup final
python3 run.py -m 8658 -t Croatia -s eventing -k pass_value
python3 run.py -m 8658 -t France -s eventing -k pass_value

python3 run.py -m 8658 -t Croatia -s eventing -k basic
python3 run.py -m 8658 -t France -s eventing -k basic


# Tracking: Game 1
python3 run.py -m 1 -t Home -s tracking -k tracking -c attacking -b opponent_half
python3 run.py -m 1 -t Away -s tracking -k tracking -c attacking -b opponent_half
python3 run.py -m 1 -t Home -s tracking -k tracking -c attacking
python3 run.py -m 1 -t Away -s tracking -k tracking -c attacking

python3 run.py -m 1 -t Home -s tracking -k tracking -c defending -b own_half
python3 run.py -m 1 -t Away -s tracking -k tracking -c defending -b own_half
python3 run.py -m 1 -t Home -s tracking -k tracking -c defending
python3 run.py -m 1 -t Away -s tracking -k tracking -c defending

python3 run.py -m 1 -t Home -s tracking -k tracking
python3 run.py -m 1 -t Away -s tracking -k tracking

python3 run.py -m 1 -t Home -s tracking -k basic
python3 run.py -m 1 -t Away -s tracking -k basic