Workflow:
 * Get an original `Intro.bin` file (in fact, back up all the contents of Teddy)
 * Record your new audio in `audio.wav` at 16kHz
 * Convert this file to the cloudpets format `audio.bin` using https://github.com/pdjstone/cloudpets-web-bluetooth/blob/master/cp_encode.py
   * you'll need a compatible libAudio32Encoder.so which is beyond the scope of this README
   * reportedly https://m.apkpure.com/wiggy-toy-app/com.spiraltoys.wiggypiggy works on modern Android arm64 devices; use termux to get a commandline environment
   * these files are also called AU files due to their magic number but this is different than the Sun "AU" format of the early 90s.
 * Create a json mouth position file using rhubarb: `rhubarb -f json -o mouth.json audio.wav`, or create a compatible file any way you like
 * Create the new Intro.bin file: `python3 earpatch.py  --au audio.au --rhubarb-json mouth.json --random-eyes orig/Intro.bin Intro.bin`
 * Plug in Teddy and copy the new Intro.bin to the Books folder
 * Eject / Safely Remove the drive
 * Power Teddy off and back on

Your new file will be played in lieu of the original Intro.

The eye movements are just random at this time, and the length of the original animations is not respected so sometimes the eye positions jump.

License: MIT
