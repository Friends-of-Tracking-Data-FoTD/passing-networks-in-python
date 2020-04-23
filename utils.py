#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 2020

@author: Sergio Llana (@SergioMinuto90)
@author: Laurie Shaw (@EightyFivePoint)
"""


import pandas as pd
import csv as csv
import argparse
import json
import sys


def parse_args():
    '''
    Parse command line arguments for plot customization
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--match-id', dest='match_id', help='Match ID', required=True)
    parser.add_argument('-t', '--team-name', dest='team_name', help='Selected team in match', required=True)
    parser.add_argument('-s', '--source', dest='source', help='Data source', choices=["eventing", "tracking"], required=True)
    parser.add_argument('-k', '--plot-type', dest='plot_type', help='Type of plot', choices=["basic", "pass_value", "tracking"], required=True)
    parser.add_argument('-b', '--ball-location', dest='half', help='Filter on the location of the ball', choices=["own_half", "opponent_half"])
    parser.add_argument('-c', '--context', dest='context', help='Whether the team is attacking or defending', choices=["attacking", "defending"])
    args = parser.parse_args(sys.argv[1:])

    if args.source == "eventing" and args.plot_type == "tracking":
        print("ERROR: Cannot plot players based on true average position with eventing data")
        return None
    elif args.source == "eventing" and (getattr(args, "context", None) or getattr(args, "half", None)):
        print("ERROR: Cannot filter player location in plot based on context or ball position")
        return None
    elif args.source == "tracking" and args.plot_type == "pass_value":
        print("ERROR: Cannot compute pass value on tracking data")
        return None

    return args


def read_json(path):
    '''
    Read JSON file from path
    '''
    return json.loads(read(path))


def read(path):
    '''
    Read content of a file
    '''
    with open(path, 'r') as f:
        return f.read()


def to_single_playing_direction(home, away, events):
    '''
    Flip coordinates in second half so that each team always shoots in the same direction through the match.
    '''
    for team in [home, away, events]:
        second_half_idx = team.Period.idxmax(2)
        columns = [c for c in team.columns if c[-1].lower() in ['x', 'y']]
        team.loc[second_half_idx:, columns] = team.loc[second_half_idx:, columns].apply(lambda x: 1-x, axis=1)

    return home, away, events


"""
----------------------
Laurie's methods below
----------------------
"""


def read_match_data(DATADIR, gameid):
    '''
    read_match_data(DATADIR,gameid):
    read all Metrica match data (tracking data for home & away teams, and ecvent data)
    '''
    tracking_home = tracking_data(DATADIR, gameid, 'Home')
    tracking_away = tracking_data(DATADIR, gameid, 'Away')
    events = read_event_data(DATADIR, gameid)
    return tracking_home, tracking_away, events


def read_event_data(DATADIR, game_id):
    '''
    read_event_data(DATADIR,game_id):
    read Metrica event data  for game_id and return as a DataFrame
    '''
    eventfile = 'Sample_Game_%s/Sample_Game_%s_RawEventsData.csv' % (game_id, game_id)  # filename
    events = pd.read_csv('{}/{}'.format(DATADIR, eventfile))  # read data
    return events


def tracking_data(DATADIR, game_id, teamname):
    '''
    tracking_data(DATADIR,game_id,teamname):
    read Metrica tracking data for game_id and return as a DataFrame.
    teamname is the name of the team in the filename. For the sample data this is either 'Home' or 'Away'.
    '''
    teamfile = 'Sample_Game_%s/Sample_Game_%s_RawTrackingData_%s_Team.csv' % (game_id, game_id, teamname)
    # First:  deal with file headers so that we can get the player names correct
    csvfile = open('{}/{}'.format(DATADIR, teamfile), 'r')  # create a csv file reader
    reader = csv.reader(csvfile)
    teamnamefull = next(reader)[3].lower()
    # construct column names
    jerseys = [x for x in next(reader) if x != '']  # extract player jersey numbers from second row
    columns = next(reader)
    for i, j in enumerate(jerseys):  # create x & y position column headers for each player
        columns[i * 2 + 3] = "{}_{}_x".format(teamname, j)
        columns[i * 2 + 4] = "{}_{}_y".format(teamname, j)
    columns[-2] = "ball_x"  # column headers for the x & y positions of the ball
    columns[-1] = "ball_y"
    # Second: read in tracking data and place into pandas Dataframe
    tracking = pd.read_csv('{}/{}'.format(DATADIR, teamfile), names=columns, index_col='Frame', skiprows=3)
    return tracking


def merge_tracking_data(home, away):
    '''
    merge home & away tracking data files into single data frame
    '''
    return home.drop(columns=['ball_x', 'ball_y']).merge(away, left_index=True, right_index=True)


def to_metric_coordinates(data, field_dimen=(106., 68.)):
    '''
    Convert positions from Metrica units to meters (with origin at centre circle)
    '''
    x_columns = [c for c in data.columns if c[-1].lower() == 'x']
    y_columns = [c for c in data.columns if c[-1].lower() == 'y']
    data[x_columns] = (data[x_columns] - 0.5) * field_dimen[0]
    data[y_columns] = -1 * (data[y_columns] - 0.5) * field_dimen[1]
    ''' 
    ------------ ***NOTE*** ------------
    Metrica actually define the origin at the *top*-left of the field, not the bottom-left, as discussed in the YouTube video. 
    I've changed the line above to reflect this. It was originally:
    data[y_columns] = ( data[y_columns]-0.5 ) * field_dimen[1]
    ------------ ********** ------------
    '''
    return data