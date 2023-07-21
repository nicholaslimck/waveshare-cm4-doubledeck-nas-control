"""
Select images as required
True for image1
False for image2
"""
import time
from display import Display

Select = True

display = Display()

while 1:
    if display.flgh:
        display.HMI1()
    else:
        display.HMI2()
    time.sleep(0.5)
