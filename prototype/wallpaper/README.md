# Commons Desk View: live wallpaper

This shows your seat at a Commons table on your desktop: who's at your table, who's talking, recent chat, and the whiteboard. It sits behind your normal app windows, so you can work in Word, VS Code or anything else and still see your study table.

## Wallpaper Engine (Windows, Steam)
1. Open Wallpaper Engine → **Wallpaper Editor** → **Create Wallpaper**, and pick `index.html` from this folder. Wallpaper Engine imports it as a *web* wallpaper. If you prefer, copy this whole folder into `…/steamapps/common/wallpaper_engine/projects/myprojects/` and it appears under your wallpapers, using `project.json`.
2. In the wallpaper's properties, set **Your name**, your **Seat**, the **Camera** (over your shoulder, whiteboard, or whole room), and whether to show the table panel.
3. To keep it live while you work, go to **Settings → Performance** and set *Other application focused* and *Other application maximized* to **Keep running**. Otherwise it pauses whenever an app fills the screen.
4. Snap your work app to about two-thirds of the screen (Win + →) so your table stays visible beside it.

## Other ways to run the same page
- **Lively Wallpaper** (Windows, free): Add wallpaper → choose this `index.html`.
- **Plash** (macOS): add the hosted desk-view URL as the wallpaper website.
- **A spare tablet or phone as a "desk"**: open `index.html?mode=wallpaper&name=YourName&seat=A3` in its browser and prop it up next to your laptop.
- **Inside the browser**: the full room has a **🪟 Desk view** button that pops out an always-on-top mini window (Chrome/Edge). It also carries your mic, so it's the best option when you need to talk.

## Limits of a wallpaper
- Wallpapers can't use the microphone, and you can't type into them. They're a *view* of the room. Your voice and chat stay in the browser tab or the Desk view pop-out.
- In this prototype the wallpaper shows the simulated classmates, because tabs on one machine sync through BroadcastChannel, which can't reach Wallpaper Engine's separate browser. In production it would connect to the room server with a read-only "presence" token.

three.js (MIT) is bundled so the wallpaper runs offline. See `THREE-LICENSE.txt`.
