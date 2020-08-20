# Home air quality project using components:
# * Adafruit Metro Express
# * PM2.5 Air Quality Sensor
# * Adafruit SGP30 Air Quality Sensor - VOC and eCO2
# * 3.2" TFT LCD with Touchscreen Breakout Board w/MicroSD Socket

try:
    import struct
except ImportError:
    import ustruct as struct

import gc
import time
import board
import busio
import adafruit_sgp30
import displayio
import terminalio
from adafruit_display_text import label
import adafruit_ili9341

# Release any resources currently in use for the displays
displayio.release_displays()

# SPI setup
spi = board.SPI()
tft_cs = board.D9
tft_dc = board.D10

# SGP30 setup
i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
sgp30.iaq_init()
sgp30.set_iaq_baseline(0x8973, 0x8aae)

# PM2.5 sensor setup
uart = busio.UART(board.TX, board.RX, baudrate=9600)

# Setup LCD and make display context
display_bus = displayio.FourWire(spi, command=tft_dc, chip_select=tft_cs)
display = adafruit_ili9341.ILI9341(display_bus, width=320, height=240)
splash = displayio.Group(max_size=10)
display.show(splash)

###########################################################

READ_FREQUENCY = 1
OUTPUT_FREQUENCY = 5
LOGGING = True
read_checkpoint = int(time.monotonic())
output_checkpoint = int(time.monotonic())
init_pass = True
buffer = []
pm25_buffer = []
pm25_average = "Calculating..."

def seconds_elapsed_since(checkpoint):
    return int(time.monotonic()) - checkpoint

while True:

    # only get readings every READ_FREQUENCY secs
    if seconds_elapsed_since(read_checkpoint) >= READ_FREQUENCY:
      read_checkpoint = int(time.monotonic())
    else:
      continue

    if LOGGING:
        print("eCO2 = %d ppm \t TVOC = %d ppb" % (sgp30.eCO2, sgp30.TVOC))
        print("**** Baseline values: eCO2 = 0x%x, TVOC = 0x%x"
              % (sgp30.baseline_eCO2, sgp30.baseline_TVOC))

    data = uart.read(32)  # read up to 32 bytes
    data = list(data)
    buffer += data

    while buffer and buffer[0] != 0x42:
        buffer.pop(0)

    if len(buffer) > 200:
        buffer = []  # avoid an overrun if all bad data
    if len(buffer) < 32:
        continue

    if buffer[1] != 0x4d:
        buffer.pop(0)
        continue

    frame_len = struct.unpack(">H", bytes(buffer[2:4]))[0]
    if frame_len != 28:
        buffer = []
        continue

    try:
        frame = struct.unpack(">HHHHHHHHHHHHHH", bytes(buffer[4:]))
    # Not sure why this happens but occasionally the buffer is double filled here
    # for now just flush it out and try again
    except RuntimeError:
        print("buffer overfilled, flushed")
        buffer = []
        continue

    pm10_standard, pm25_standard, pm100_standard, pm10_env, \
        pm25_env, pm100_env, particles_03um, particles_05um, particles_10um, \
        particles_25um, particles_50um, particles_100um, skip, checksum = frame

    check = sum(buffer[0:30])

    if check != checksum:
        buffer = []
        continue

    if LOGGING:
        print("Concentration Units (standard)")
        print("---------------------------------------")
        print("PM 1.0: %d\tPM2.5: %d\tPM10: %d" %
              (pm10_standard, pm25_standard, pm100_standard))
        print("Concentration Units (environmental)")
        print("---------------------------------------")
        print("PM 1.0: %d\tPM2.5: %d\tPM10: %d" % (pm10_env, pm25_env, pm100_env))
        print("---------------------------------------")
        print("Particles > 0.3um / 0.1L air:", particles_03um)
        print("Particles > 0.5um / 0.1L air:", particles_05um)
        print("Particles > 1.0um / 0.1L air:", particles_10um)
        print("Particles > 2.5um / 0.1L air:", particles_25um)
        print("Particles > 5.0um / 0.1L air:", particles_50um)
        print("Particles > 10 um / 0.1L air:", particles_100um)
        print("---------------------------------------")

    buffer = buffer[32:]

    pm25_buffer.append(pm25_env)
    length = len(pm25_buffer)
    if length > 30:
        pm25_buffer.pop(0)
    elif length < 30:
        pm25_average = "Calculating..."
    else:
        pm25_average = 0
        for value in pm25_buffer:
            pm25_average += value
        pm25_average = pm25_average/30

    # only refresh output every OUTPUT_FREQUENCY secs
    if seconds_elapsed_since(output_checkpoint) >= OUTPUT_FREQUENCY:
      output_checkpoint = int(time.monotonic())
    else:
      continue

    if init_pass:
      text_group = displayio.Group(max_size=10, scale=3, x=40, y=120)
      init_pass = False
    else: # dealloc old UI elements before drawing new ones
      text_group.pop(0)
      splash.pop(0)
      text_area = 0
      gc.collect()

#    text = ("PM2.5: %d\neCO2: %d ppm\nTVOC: %d ppb"
#            % (pm25_env, sgp30.eCO2, sgp30.TVOC))
    text = ("PM2.5: %d\n\n30 sec average:\n%s"
            % (pm25_env, str(pm25_average)))

    text_area = label.Label(terminalio.FONT, text=text, color=0xFFFF00)
    text_group.append(text_area) # Subgroup for text scaling
    splash.append(text_group)
