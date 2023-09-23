Workflow:
 * Install [rhubarb](https://github.com/DanielSWolf/rhubarb-lip-sync) and `pip install g722_1_mod`.
 * Get an original `Intro.bin` file (in fact, back up all the contents of Teddy)
 * Record your new audio in `audio.wav` at 16kHz or 32kHz sample rate
 * Create a json mouth position file using [rhubarb](https://github.com/DanielSWolf/rhubarb-lip-sync): `rhubarb -f json -o mouth.json audio.wav`, or create a compatible file any way you like
 * Create the new Intro.bin file: `python3 earpatch.py  --wav audio.wav --rhubarb-json mouth.json orig/Intro.bin Intro.bin`
   * eye animations are generated randomly by default. You can control their frequency with `--random-eyes-median` and `--random-eyes-std-dev` command line parameters.
     The default is an eye animation around once every 30s.
   * Disable eye animations with `--no-random-eyes`
 * Plug in Teddy and copy the new Intro.bin to the Books folder of the USB drive that appears
 * Eject / Safely Remove the drive
 * Power Teddy off and back on

Typical commandline:
```
python3 earpatch.py  --wav audio.wav --rhubarb-json mouth.json orig/Intro.bin Intro.bin
```

Your new file will be played in lieu of the original Intro.

Installation troubleshooting:

If you get this error:
```
Traceback (most recent call last):
  File "earpatch.py", line 170, in <module>
    earpatch()
TypeError: command.<locals>.decorator() missing 1 required positional argument: 'f'
```

Make sure you use click version 8.1 or above.
This command can help: `pip install -U click`

License: MIT
