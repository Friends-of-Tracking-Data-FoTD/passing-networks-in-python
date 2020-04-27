#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 2020

@author: Sergio Llana (@SergioMinuto90)
"""


from pandas.io.json import json_normalize
from abc import ABC, abstractmethod
import socceraction.vaep as vaep
import pandas as pd
import warnings
import os

warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

from processing import PassingNetworkBuilder
from utils import read_json


class StatsBombPassingNetwork(PassingNetworkBuilder, ABC):
    def __init__(self, args):
        self.plot_type = args.plot_type
        self.team_name = args.team_name
        self.match_id = args.match_id

        self.plot_name = None
        self.df_events = None
        self.plot_title = None
        self.names_dict = None
        self.plot_legend = None
        self.num_minutes = None
        self.player_position = None
        self.pair_pass_value = None
        self.pair_pass_count = None
        self.player_pass_value = None
        self.player_pass_count = None

    def read_data(self):
        """
        Read StatsBomb eventing data of the selected 'match_id', generating a pandas DataFrame
        with the events and a dictionary of player names and nicknames.
        """
        # Player name translation dict
        lineups = read_json("data/eventing/lineups/{0}.json".format(self.match_id))
        self.names_dict = {player["player_name"]: player["player_nickname"]
                           for team in lineups for player in team["lineup"]}

        # Pandas dataframe containing the events of the match
        events = read_json("data/eventing/events/{0}.json".format(self.match_id))
        self.df_events = json_normalize(events, sep="_").assign(match_id=self.match_id)

    def compute_total_minutes(self):
        """
        Compute the maximum number of minutes that are used for the passing network.
        The idea is not to have more/less than 11 players in the team because of substitutions or red cards.
        """
        first_red_card_minute = self.df_events[self.df_events.foul_committed_card_name.isin(["Second Yellow", "Red Card"])].minute.min()
        first_substitution_minute = self.df_events[self.df_events.type_name == "Substitution"].minute.min()
        max_minute = self.df_events.minute.max()

        self.num_minutes = min(first_substitution_minute, first_red_card_minute, max_minute)

    def set_text_info(self):
        """
        Set the plot's name, title and legend information based on the customization chosen with the command line arguments.
        """
        # Name of the .PNG in the plots/ folder
        self.plot_name = "statsbomb_match{0}_{1}_{2}".format(self.match_id, self.team_name, self.plot_type)

        # Title of the plot
        opponent_team = [x for x in self.df_events.team_name.unique() if x != self.team_name][0]
        self.plot_title ="{0}'s passing network against {1} (StatsBomb eventing data)".format(self.team_name, opponent_team)

        # Information in the legend
        color_meaning = "pass value (VAEP)" if self.plot_type == "pass_value" else "number of passes"
        self.plot_legend = "Location: pass origin\nSize: number of passes\nColor: {0}".format(color_meaning)

    @abstractmethod
    def prepare_data(self):
        pass

    @staticmethod
    def _statsbomb_to_point(location, max_width=120, max_height=80):
        '''
        Convert a point's coordinates from a StatsBomb's range to 0-1 range.
        '''
        return location[0] / max_width, 1-(location[1] / max_height)


class StatsBombBasicPassingNetwork(StatsBombPassingNetwork):
    def __init__(self, args):
        super(StatsBombBasicPassingNetwork, self).__init__(args)

    def prepare_data(self):
        """
        Prepares the five pandas DataFrames that 'draw_pass_map' needs.
        """
        # We select all successful passes done by the selected team before the minute
        # of the first substitution or red card.
        df_passes = self.df_events[(self.df_events.type_name == "Pass") &
                                   (self.df_events.pass_outcome_name.isna()) &
                                   (self.df_events.team_name == self.team_name) &
                                   (self.df_events.minute < self.num_minutes)].copy()

        # If available, use player's nickname instead of full name to optimize space in plot
        df_passes["pass_recipient_name"] = df_passes.pass_recipient_name.apply(lambda x: self.names_dict[x] if self.names_dict[x] else x)
        df_passes["player_name"] = df_passes.player_name.apply(lambda x: self.names_dict[x] if self.names_dict[x] else x)

        # In this type of plot, both the size and color (i.e. value) mean the same: number of passes
        self.player_pass_count = df_passes.groupby("player_name").size().to_frame("num_passes")
        self.player_pass_value = df_passes.groupby("player_name").size().to_frame("pass_value")

        # 'pair_key' combines the names of the passer and receiver of each pass (sorted alphabetically)
        df_passes["pair_key"] = df_passes.apply(lambda x: "_".join(sorted([x["player_name"], x["pass_recipient_name"]])), axis=1)
        self.pair_pass_count = df_passes.groupby("pair_key").size().to_frame("num_passes")
        self.pair_pass_value = df_passes.groupby("pair_key").size().to_frame("pass_value")

        # Average pass origin's coordinates for each player
        df_passes["origin_pos_x"] = df_passes.location.apply(lambda x: self._statsbomb_to_point(x)[0])
        df_passes["origin_pos_y"] = df_passes.location.apply(lambda x: self._statsbomb_to_point(x)[1])
        self.player_position = df_passes.groupby("player_name").agg({"origin_pos_x": "median", "origin_pos_y": "median"})


class StatsBombValuePassingNetwork(StatsBombPassingNetwork):
    def __init__(self, args):
        super(StatsBombValuePassingNetwork, self).__init__(args)

        # This data must be prepared on advance by running the 'prepare_vaep.py' script
        self.predictions_h5 = os.path.join("data/eventing", "predictions.h5")

        spadl_h5 = os.path.join("data/eventing", "spadl-statsbomb.h5")
        self.actiontypes = pd.read_hdf(spadl_h5, "actiontypes")
        self.bodyparts = pd.read_hdf(spadl_h5, "bodyparts")
        self.results = pd.read_hdf(spadl_h5, "results")
        self.players = pd.read_hdf(spadl_h5, "players")
        self.teams = pd.read_hdf(spadl_h5, "teams")

        self.actions = pd.read_hdf(spadl_h5, "actions/game_{0}".format(self.match_id))

    def prepare_data(self):
        """
        Prepares the five pandas DataFrames that 'draw_pass_map' needs.
        """
        # We select all successful passes done by the selected team before the minute
        # of the first substitution or red card.
        df_passes = self.df_events[(self.df_events.type_name == "Pass") &
                                   (self.df_events.pass_outcome_name.isna()) &
                                   (self.df_events.team_name == self.team_name) &
                                   (self.df_events.minute < self.num_minutes)].copy()

        # If available, use player's nickname instead of full name to optimize space in plot
        df_passes["pass_recipient_name"] = df_passes.pass_recipient_name.apply(lambda x: self.names_dict[x] if self.names_dict[x] else x)
        df_passes["player_name"] = df_passes.player_name.apply(lambda x: self.names_dict[x] if self.names_dict[x] else x)

        # Set the VAEP metric to each pass
        actions = (
            self.actions.merge(self.actiontypes,how="left")
                   .merge(self.results,how="left")
                   .merge(self.bodyparts,how="left")
                   .merge(self.players,how="left")
                   .merge(self.teams,how="left")
        )

        preds = pd.read_hdf(self.predictions_h5, "game_{0}".format(self.match_id))
        values = vaep.value(actions, preds.scores, preds.concedes)
        df_vaep = pd.concat([actions, preds, values], axis=1)
        df_vaep["player_name"] = df_vaep.apply(lambda x: x["player_nickname"] if x["player_nickname"] else x["player_name"], axis=1)

        df_result = pd.merge(df_passes[["timestamp", "player_name", "pass_recipient_name"]], df_vaep, on=["timestamp", "player_name"], how="left")
        df_result["vaep_value"] = df_result.vaep_value.apply(lambda x: x if x >= 0 else None)  # Filter out negative actions
        df_result["vaep_value"] = df_result.vaep_value.apply(lambda x: x if x >= 0 else None)  # Filter out negative actions

        # Aggregate number of passes and VAEP metric for each player
        self.player_pass_count = df_result.groupby("player_name").size().to_frame("num_passes")
        self.player_pass_value = df_result.groupby("player_name").agg(pass_value=("vaep_value", "mean"))

        # Average pass origin's coordinates for each player
        df_passes["origin_pos_x"] = df_passes.location.apply(lambda x: self._statsbomb_to_point(x)[0])
        df_passes["origin_pos_y"] = df_passes.location.apply(lambda x: self._statsbomb_to_point(x)[1])
        self.player_position = df_passes.groupby("player_name").agg({"origin_pos_x": "median", "origin_pos_y": "median"})

        # 'pair_key' combines the names of the passer and receiver of each pass (sorted alphabetically)
        df_result["pair_key"] = df_result.apply(lambda x: "_".join(sorted([x["player_name"], x["pass_recipient_name"]])), axis=1)
        self.pair_pass_value = df_result.groupby("pair_key").agg(pass_value=("vaep_value", "mean"))
        self.pair_pass_count = df_result.groupby("pair_key").size().to_frame("num_passes")
