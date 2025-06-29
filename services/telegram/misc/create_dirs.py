import logging
import os

dirs = ["./data/old_panics", "./data/old_cities", "./data/tmp"]


def create_dirs():
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        logging.info(f"Create dir {d}")