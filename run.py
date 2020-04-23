#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr 19 2020

@author: Sergio Llana (@SergioMinuto90)
"""


from processing.eventing import StatsBombBasicPassingNetwork, StatsBombValuePassingNetwork
from processing.tracking import MetricaBasicPassingNetwork, MetricaTrackingPassingNetwork
from utils import parse_args


def main(args):
    '''
    Instantiates a Passing Network Builder depending on the type of plot selected with the arguments
    in the command line.
    '''
    if args.source == "eventing":
        if args.plot_type == "pass_value":
            plot_builder = StatsBombValuePassingNetwork(args)
        else:
            plot_builder = StatsBombBasicPassingNetwork(args)
    else:
        if args.plot_type == "tracking":
            plot_builder = MetricaTrackingPassingNetwork(args)
        else:
            plot_builder = MetricaBasicPassingNetwork(args)

    plot_builder.build_and_save()


if __name__ == "__main__":
    parsed_args = parse_args()
    if parsed_args:
        main(parsed_args)
