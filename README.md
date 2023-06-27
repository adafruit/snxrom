Workflow:
 * Get an original `Intro.bin` file (in fact, back up all the contents of Teddy)
 * Record your new audio in `audio.wav` at 16kHz
 * Convert this file to the cloudpets format `audio.bin` using https://github.com/pdjstone/cloudpets-web-bluetooth/blob/master/cp\_encode.py
   * you'll need a compatible libAudio32Encoder.so which is beyond the scope of this README
   * reportedly https://m.apkpure.com/wiggy-toy-app/com.spiraltoys.wiggypiggy works on modern Android arm64 devices; use termux to get a commandline environment
   * these files are also called AU files due to their magic number but this is different than the Sun "AU" format of the early 90s.
 * Create a json mouth position file using [rhubarb](https://github.com/DanielSWolf/rhubarb-lip-sync): `rhubarb -f json -o mouth.json audio.wav`, or create a compatible file any way you like
 * Create the new Intro.bin file: `python3 earpatch.py  --au audio.au --rhubarb-json mouth.json --random-eyes orig/Intro.bin Intro.bin`
   * eye animations are generated randomly by default, but you can control their frequency with `--random-eyes-median` and `--random-eyes-std-dev` command line parameters.
     The default is an eye animation around once every 30s.
 * Plug in Teddy and copy the new Intro.bin to the Books folder of the USB drive that appears
 * Eject / Safely Remove the drive
 * Power Teddy off and back on

Your new file will be played in lieu of the original Intro.

License: MIT
