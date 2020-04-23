#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 2020

@author: Sergio Llana (@SergioMinuto90)
"""


from abc import ABC, abstractmethod
import pandas as pd

from utils import read_json, read_event_data, tracking_data, to_single_playing_direction
from processing import PassingNetworkBuilder


class MetricaPassingNetwork(PassingNetworkBuilder, ABC):
    def __init__(self, args):
        self.context = getattr(args, "context", None)
        self.half = getattr(args, "half", None)
        self.plot_type = args.plot_type
        self.team_name = args.team_name
        self.match_id = args.match_id

        self.plot_name = None
        self.df_events = None
        self.plot_title = None
        self.plot_legend = None
        self.df_tracking = None
        self.num_minutes = None
        self.player_position = None
        self.pair_pass_value = None
        self.pair_pass_count = None
        self.player_pass_value = None
        self.player_pass_count = None

    def read_data(self):
        """
        Read Metrica eventing and tracking data of the selected 'match_id', generating two pandas DataFrames.
        Data's X coordinate must be reversed in the second period, as we need the same attacking direction in both periods.
        """
        data_path = "data/tracking"

        # Read both tracking and eventing data
        df_events = read_event_data(data_path, self.match_id)
        df_events['Minute'] = df_events['Start Time [s]'] / 60.0

        df_tracking_home = tracking_data(data_path, self.match_id, "Home")
        df_tracking_away = tracking_data(data_path, self.match_id, "Away")
        df_tracking_home, df_tracking_away, df_events = to_single_playing_direction(df_tracking_home, df_tracking_away, df_events)

        self.df_events = df_events
        self.df_tracking = df_tracking_home if self.team_name == "Home" else df_tracking_away

    def compute_total_minutes(self):
        """
        Compute the maximum number of minutes that are used for the passing network.
        The idea is not to have more/less than 11 players in the team because of substitutions or red cards.

        As Metrica does not provide an event type for substitutions, tracking data is used to know when the first
        player is introduced in the pitch (player number 12), as he would not have NaN in his column anymore.
        """
        max_minute = self.df_events["Minute"].max()
        first_substitution_player = self.df_tracking.columns[24]
        first_substitution_minute = self.df_tracking[~self.df_tracking[first_substitution_player].isna()]["Time [s]"].min()/60.0
        first_red_card_minute = self.df_events[(self.df_events["Type"] == "CARD") & (self.df_events["Subtype"] == "RED")]["Minute"].min()

        self.num_minutes = min(first_substitution_minute, first_red_card_minute, max_minute)

    def set_text_info(self):
        """
        Set the plot's name, title and legend information based on the customization chosen with the command line arguments.
        """
        # Name of the .PNG in the plots/ folder
        self.plot_name = "metrica_match{0}_{1}_{2}".format(self.match_id, self.team_name, self.plot_type)

        # Title of the plot
        opponent_team = "Away" if self.team_name == "Home" else "Home"
        self.plot_title ="{0}'s passing network against {1} (Metrica Sports tracking data)".format(self.team_name, opponent_team)

        # Information in the legend
        if self.context or self.half:
            context_meaning = "Context: "
            if self.context and not self.half:
                context_meaning += self.context
            elif not self.context and self.half:
                ball_team = self.team_name if self.half == "own_half" else opponent_team
                context_meaning += "ball in {0}'s half".format(ball_team)
            else:
                ball_team = self.team_name if self.half == "own_half" else opponent_team
                context_meaning += "{0}, ball in {1}'s half".format(self.context, ball_team)
            context_meaning += "\n"
        else:
            context_meaning = ""

        location_meaning = "players avg. position" if self.plot_type == "tracking" else "pass origin"
        self.plot_legend = "{0}Location: {1}\nSize: number of passes\nColor: number of passes".format(context_meaning, location_meaning)

    @abstractmethod
    def prepare_data(self):
        pass


class MetricaBasicPassingNetwork(MetricaPassingNetwork):
    def __init__(self, args):
        super(MetricaBasicPassingNetwork, self).__init__(args)

    def prepare_data(self):
        """
        Prepares the five pandas DataFrames that 'draw_pass_map' needs.
        """
        # We select all passes done by the selected team before the minute of the first substitution or red card.
        df_passes = self.df_events[(self.df_events["Type"] == "PASS") &
                                   (self.df_events["Team"] == self.team_name) &
                                   (self.df_events["Minute"] < self.num_minutes)].copy()

        df_passes = df_passes.rename(columns={"Start X": "origin_pos_x", "Start Y": "origin_pos_y"})

        # In this type of plot, both the size and color (i.e. value) mean the same: number of passes
        self.player_pass_value = df_passes.groupby("From").size().to_frame("pass_value")
        self.player_pass_count = df_passes.groupby("From").size().to_frame("num_passes")

        # 'pair_key' combines the names of the passer and receiver of each pass (sorted alphabetically)
        df_passes["pair_key"] = df_passes.apply(lambda x: "_".join(sorted([x["From"], x["To"]])), axis=1)
        self.pair_pass_value = df_passes.groupby("pair_key").size().to_frame("pass_value")
        self.pair_pass_count = df_passes.groupby("pair_key").size().to_frame("num_passes")

        # Average pass origin's coordinates for each player
        self.player_position = df_passes.groupby("From").agg({"origin_pos_x": "median", "origin_pos_y": "median"})


class MetricaTrackingPassingNetwork(MetricaPassingNetwork):
    def __init__(self, args):
        super(MetricaTrackingPassingNetwork, self).__init__(args)

    def _context_frames(self):
        """
        Basic algorithm to detect ball possession changes.
        Note that frames out of effective playing time are not considered.

        Returns
        -----------
            on_ball_frames: set of frames when the selected team was in possession of the ball (i.e. attacking).
            off_ball_frames: set of frames when the selected team had not the possession (i.e. defending).
        """
        df_events_simple = self.df_events[~self.df_events.Type.isin(["CHALLENGE", "CARD"])].reset_index(drop=True)
        possession_start_events = ['PASS', 'RECOVERY', 'SET PIECE', 'SHOT']
        possession_change_events = ["BALL LOST", "BALL OUT"]

        current_window_start = self.df_events[self.df_events["Subtype"] == "KICK OFF"].iloc[0]["Start Frame"]

        on_ball_frames = set()
        off_ball_frames = set()
        for event_index, row in df_events_simple.iterrows():
            event_type = row["Type"]
            if event_type in possession_change_events:
                current_window_end = row["Start Frame"] if event_type == "BALL OUT" else row["End Frame"]

                next_starts = df_events_simple[(df_events_simple.index > event_index) &
                                               (df_events_simple.index <= event_index + 10) &
                                               (df_events_simple["Type"].isin(possession_start_events))]

                if next_starts.shape[0] > 0:
                    next_start = next_starts.iloc[0]

                    frames_set = on_ball_frames if row["Team"] == self.team_name else off_ball_frames
                    frames_set.update(range(current_window_start, current_window_end))

                    current_window_start = next_start["Start Frame"]

        return on_ball_frames, off_ball_frames

    def prepare_data(self):
        """
        Prepares the five pandas DataFrames that 'draw_pass_map' needs.
        """
        df_passes = self.df_events[(self.df_events["Type"] == "PASS") &
                                   (self.df_events["Team"] == self.team_name) &
                                   (self.df_events["Minute"] < self.num_minutes)].copy()

        df_passes = df_passes.rename(columns={"Start X": "origin_pos_x", "Start Y": "origin_pos_y"})

        # In this type of plot, both the size and color (i.e. value) mean the same: number of passes
        self.player_pass_value = df_passes.groupby("From").size().to_frame("pass_value")
        self.player_pass_count = df_passes.groupby("From").size().to_frame("num_passes")

        # 'pair_key' combines the names of the passer and receiver of each pass (sorted alphabetically)
        df_passes["pair_key"] = df_passes.apply(lambda x: "_".join(sorted([x["From"], x["To"]])), axis=1)
        self.pair_pass_value = df_passes.groupby("pair_key").size().to_frame("pass_value")
        self.pair_pass_count = df_passes.groupby("pair_key").size().to_frame("num_passes")

        # In this type of plot, instead of averaging the location of the pass origins, we use tracking data
        # to compute player's average location
        df_tracking = self.df_tracking[(self.df_tracking.index < df_passes["End Frame"].max())]
        x_columns = [col for col in df_tracking.columns if col.endswith("_x") and col != "ball_x"]
        y_columns = [col for col in df_tracking.columns if col.endswith("_y") and col != "ball_y"]

        # Different filters are applied depending on the customization chosen in the command line arguments
        if self.context == "attacking":
            frames, _ = self._context_frames()
            df_tracking = df_tracking[df_tracking.index.isin(frames)]
            self.plot_name = "{0}_{1}".format(self.plot_name, self.context)
        elif self.context == "defending":
            _, frames = self._context_frames()
            df_tracking = df_tracking[df_tracking.index.isin(frames)]
            self.plot_name = "{0}_{1}".format(self.plot_name, self.context)

        if self.half:
            match_start = self.df_events[self.df_events["Subtype"] == "KICK OFF"].iloc[0]["Start Frame"]
            mean_x = self.df_tracking.loc[self.df_tracking.index == match_start, x_columns].mean().mean()

            if self.half == "own_half":
                if mean_x < 0.5:
                    df_tracking = df_tracking[df_tracking["ball_x"] < 0.5]
                else:
                    df_tracking = df_tracking[df_tracking["ball_x"] >= 0.5]

                self.plot_name = "{0}_{1}".format(self.plot_name, self.half)
            else:
                if mean_x < 0.5:
                    df_tracking = df_tracking[df_tracking["ball_x"] >= 0.5]
                else:
                    df_tracking = df_tracking[df_tracking["ball_x"] < 0.5]

                self.plot_name = "{0}_{1}".format(self.plot_name, self.half)

        df_pos_x = pd.melt(df_tracking, id_vars=[], value_vars=x_columns)
        df_pos_x["player"] = df_pos_x.variable.apply(lambda x: x[:-2])
        df_pos_x = df_pos_x.groupby("player").agg({"value": "median"})
        df_pos_x = df_pos_x.rename(columns={"value": "origin_pos_x"})

        df_pos_y = pd.melt(df_tracking, id_vars=[], value_vars=y_columns)
        df_pos_y["player"] = df_pos_y.variable.apply(lambda x: x[:-2])
        df_pos_y = df_pos_y.groupby("player").agg({"value": "median"})
        df_pos_y = df_pos_y.rename(columns={"value": "origin_pos_y"})

        player_position = df_pos_x.merge(df_pos_y, left_index=True, right_index=True)
        player_position.index = player_position.index.map(lambda x: "Player{0}".format(x.split("_")[-1]))
        self.player_position = player_position