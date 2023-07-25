import logging
import time

from display import Display


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s | %(levelname)s | %(name)s | %(message)s', level=logging.INFO)

    display = Display()
    display.render()
