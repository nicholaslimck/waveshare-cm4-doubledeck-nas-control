import RPi.GPIO as GPIO
import time

if __name__ == '__main__':
    pwmPin = 19
    fgPin = 17

    freq = 1000
    dc = 50
    onGetSpeed = False

    global t1, t
    t1 = 0
    t = 1

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pwmPin, GPIO.OUT)
    GPIO.setup(fgPin, GPIO.IN)

    pwm = GPIO.PWM(pwmPin, freq)
    pwm.start(dc)


def startGetSpeed():
    GPIO.add_event_detect(fgPin, GPIO.FALLING, speedcallback)
    onGetSpeed = True


def stopGetSpeed():
    GPIO.remove_event_detect(fgPin)
    onGetSpeed = False


def speedcallback(fgPin):
    global t1, t
    if t1 != 0:
        t = time.time() - t1
        t1 = 0
    else:
        t1 = time.time()


def getTemp():
    f = open('/sys/class/thermal/thermal_zone0/temp')
    return int(f.read()) / 1000.0


def autoSpeed(dc, temp):
    if temp < 45 and dc >= 10:
        return dc - 10
    elif temp > 55 and dc <= 90:
        return dc + 10
    else:
        return dc
    return dc


try:
    # freq = int(input("Please input the freq of PWM: "))
    pwm.ChangeFrequency(freq)
    pwm.ChangeDutyCycle(dc)
    startGetSpeed()
    num = 10
    while True:
        # dc = int(input("Please input the duty cycle(0-100): "))
        # pwm.ChangeDutyCycle(dc)

        speed = 60 / (t * 2)
        temp = getTemp()
        print("The speed is %f" % speed)
        print("The temp is %f" % temp)
        print("\33[3A")
        if num > 5:
            num = 0
            dc = autoSpeed(dc, temp)
            pwm.ChangeDutyCycle(dc)
        num = num + 1
        time.sleep(1)
    pwm.stop()
    stopGetSpeed()
    GPIO.cleanup()

except KeyboardInterrupt as e:
    pwm.stop()
    stopGetSpeed()
    GPIO.cleanup()
    exit()
