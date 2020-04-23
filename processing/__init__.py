#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 2020

@author: Sergio Llana (@SergioMinuto90)
"""


from abc import ABC, abstractmethod
import matplotlib.pyplot as plt

from visualization.passing_network import draw_pitch, draw_pass_map


class PassingNetworkBuilder(ABC):
    """
    Abstract class that defines a template method containing a skeleton of
    the code for building a passing network plot.

    Concrete subclasses should implement these operations for specific data
    sources (e.g. eventing vs tracking).
    """
    def build_and_save(self):
        """
        Template of the algorithm.
        """
        self.read_data()
        self.compute_total_minutes()
        self.set_text_info()
        self.prepare_data()
        self.build_plot()

        print("{0} done!".format(self.plot_name))

    @abstractmethod
    def read_data(self):
        pass

    @abstractmethod
    def compute_total_minutes(self):
        pass

    @abstractmethod
    def set_text_info(self):
        pass

    @abstractmethod
    def prepare_data(self):
        pass

    def build_plot(self):
        """
        Plot the pitch and passing network, saving the output image into the 'plots' folder.
        """
        ax = draw_pitch()
        draw_pass_map(ax, self.player_position, self.player_pass_count, self.player_pass_value,
                      self.pair_pass_count, self.pair_pass_value, self.plot_title, self.plot_legend)

        plt.savefig("plots/{0}.png".format(self.plot_name))
