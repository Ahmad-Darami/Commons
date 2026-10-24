#!/usr/bin/env python3
"""Rebuilds wallpaper/index.html from index.html: offline three.js, desk-display mode on by default."""
import os
here = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(here, 'index.html')).read()
for a, b in [('<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>', '<script src="three.min.js"></script>'),
             ('<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>', '<script src="GLTFLoader.js"></script>'),
             ('<title>Commons Room Prototype</title>', "<title>Commons Desk View</title>\n<script>window.COMMONS_MODE = 'wallpaper';</script>")]:
    assert s.count(a) == 1, a
    s = s.replace(a, b)
open(os.path.join(here, 'wallpaper', 'index.html'), 'w').write(s)
print('wrote wallpaper/index.html')
