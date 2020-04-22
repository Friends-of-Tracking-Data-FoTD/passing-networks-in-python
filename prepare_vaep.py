#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 2020

Code borrowed and adapted from https://github.com/ML-KULeuven/socceraction

@author: Sergio Llana (@SergioMinuto90)
"""


import socceraction.classification.features as fs
import socceraction.classification.labels as lab
import socceraction.spadl.statsbomb as statsbomb
import socceraction.spadl as spadl

import pandas as pd
import warnings
import xgboost
import tqdm
import os

warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)
datafolder = "data/eventing"


### NOTEBOOK 1: LOAD AND CONVERT STATSBOMB DATA
SBL = statsbomb.StatsBombLoader(root=datafolder, getter="local")
selected_competitions = SBL.competitions()

# Get matches from all selected competitions
matches = list(SBL.matches(row.competition_id, row.season_id)
               for row in selected_competitions.itertuples())

matches = pd.concat(matches, sort=True).reset_index(drop=True)

# Load and convert match data
matches_verbose = tqdm.tqdm(list(matches.itertuples()), desc="Loading match data")
teams, players, player_games = [], [], []
actions = {}

for match in matches_verbose:
    teams.append(SBL.teams(match.match_id))
    players.append(SBL.players(match.match_id))
    events = SBL.events(match.match_id)

    player_games.append(statsbomb.extract_player_games(events))
    actions[match.match_id] = statsbomb.convert_to_actions(events, match.home_team_id)

# Store converted spadl data in a h5-file
games = matches.rename(columns={"match_id": "game_id"})
teams = pd.concat(teams, sort=True).drop_duplicates("team_id").reset_index(drop=True)
players = pd.concat(players, sort=True).drop_duplicates("player_id").reset_index(drop=True)
player_games = pd.concat(player_games, sort=True).reset_index(drop=True)

spadl_h5 = os.path.join(datafolder, "spadl-statsbomb.h5")
with pd.HDFStore(spadl_h5) as spadlstore:
    spadlstore["competitions"] = selected_competitions
    spadlstore["games"] = games
    spadlstore["teams"] = teams
    spadlstore["players"] = players
    spadlstore["player_games"] = player_games
    for game_id in actions.keys():
        spadlstore["actions/game_{0}".format(game_id)] = actions[game_id]

    spadlstore["actiontypes"] = spadl.actiontypes_df()
    spadlstore["results"] = spadl.results_df()
    spadlstore["bodyparts"] = spadl.bodyparts_df()


### NOTEBOOK 2: COMPUTE FEATURES AND LABELS
spadl_h5 = os.path.join(datafolder,"spadl-statsbomb.h5")
features_h5 = os.path.join(datafolder, "features.h5")
labels_h5 = os.path.join(datafolder, "labels.h5")

actiontypes = pd.read_hdf(spadl_h5, "actiontypes")
bodyparts = pd.read_hdf(spadl_h5, "bodyparts")
results = pd.read_hdf(spadl_h5, "results")

xfns = [
    fs.actiontype,
    fs.actiontype_onehot,
    fs.bodypart,
    fs.bodypart_onehot,
    fs.result,
    fs.result_onehot,
    fs.goalscore,
    fs.startlocation,
    fs.endlocation,
    fs.movement,
    fs.space_delta,
    fs.startpolar,
    fs.endpolar,
    fs.team,
    fs.time,
    fs.time_delta
]

for game in tqdm.tqdm(list(games.itertuples()), desc="Generating and storing features in {0}".format(features_h5)):
    actions = pd.read_hdf(spadl_h5, "actions/game_{0}".format(game.game_id))
    actions = (
        actions.merge(actiontypes, how="left")
               .merge(results, how="left")
               .merge(bodyparts, how="left")
               .reset_index(drop=True)
    )
    gamestates = fs.gamestates(actions, 3)
    gamestates = fs.play_left_to_right(gamestates, game.home_team_id)

    X = pd.concat([fn(gamestates) for fn in xfns], axis=1)
    X.to_hdf(features_h5, "game_{0}".format(game.game_id))

yfns = [lab.scores, lab.concedes, lab.goal_from_shot]

for game in tqdm.tqdm(list(games.itertuples()), desc="Computing and storing labels in {0}".format(labels_h5)):
    actions = pd.read_hdf(spadl_h5, "actions/game_{0}".format(game.game_id))
    actions = (
        actions.merge(actiontypes, how="left")
            .merge(results, how="left")
            .merge(bodyparts, how="left")
            .reset_index(drop=True)
    )

    Y = pd.concat([fn(actions) for fn in yfns], axis=1)
    Y.to_hdf(labels_h5, "game_{0}".format(game.game_id))


### NOTEBOOK 3: COMPUTE FEATURES AND LABELS
predictions_h5 = os.path.join(datafolder, "predictions.h5")
spadl_h5 = os.path.join(datafolder, "spadl-statsbomb.h5")
features_h5 = os.path.join(datafolder, "features.h5")
labels_h5 = os.path.join(datafolder, "labels.h5")

games = pd.read_hdf(spadl_h5, "games")

actiontypes = pd.read_hdf(spadl_h5, "actiontypes")
bodyparts = pd.read_hdf(spadl_h5, "bodyparts")
results = pd.read_hdf(spadl_h5, "results")

# 1. Select feature set X
xfns = [
    fs.actiontype,
    fs.actiontype_onehot,
    fs.bodypart_onehot,
    fs.result,
    fs.result_onehot,
    fs.goalscore,
    fs.startlocation,
    fs.endlocation,
    fs.movement,
    fs.space_delta,
    fs.startpolar,
    fs.endpolar,
    fs.team,
    fs.time_delta,
]

nb_prev_actions = 1

# Generate the columns of the selected features
Xcols = fs.feature_column_names(xfns, nb_prev_actions)
X = []
for game_id in tqdm.tqdm(games.game_id, desc="selecting features"):
    Xi = pd.read_hdf(features_h5, "game_{0}".format(game_id))
    X.append(Xi[Xcols])

X = pd.concat(X)

# 2. Select label Y
Ycols = ["scores", "concedes"]
Y = []
for game_id in tqdm.tqdm(games.game_id, desc="selecting label"):
    Yi = pd.read_hdf(labels_h5, "game_{0}".format(game_id))
    Y.append(Yi[Ycols])

Y = pd.concat(Y)

# 3. train classifiers F(X) = Y
Y_hat = pd.DataFrame()
models = {}
for col in list(Y.columns):
    model = xgboost.XGBClassifier()
    model.fit(X,Y[col])
    models[col] = model

Y_hat = pd.DataFrame()
for col in Y.columns:
    Y_hat[col] = [p[1] for p in models[col].predict_proba(X)]

# Save predictions
A = []
for game_id in tqdm.tqdm(games.game_id, "loading game ids"):
    Ai = pd.read_hdf(spadl_h5, "actions/game_{0}".format(game_id))
    A.append(Ai[["game_id"]])

A = pd.concat(A)
A = A.reset_index(drop=True)

# Concatenate action game id rows with predictions and save per game
grouped_predictions = pd.concat([A, Y_hat], axis=1).groupby("game_id")
for k, df in tqdm.tqdm(grouped_predictions, desc="saving predictions per game"):
    df = df.reset_index(drop=True)
    df[Y_hat.columns].to_hdf(predictions_h5, "game_{0}".format(int(k)))
