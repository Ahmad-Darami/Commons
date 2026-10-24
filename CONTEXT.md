# Commons

A browser-based study space where remote students meet inside faithful replicas of real Penn State rooms.

## Language

**Customer**:
Penn State, the institution that buys and deploys Commons.
_Avoid_: client, user

**Student**:
A World Campus learner who uses Commons to study with others.
_Avoid_: user, member

**Room**:
A shared virtual space that faithfully replicates a specific real Penn State space, created by scanning that space with an iPhone.
_Avoid_: environment, world, map, level

**Scan**:
One walk-through of a real Penn State space with an iPhone Pro. A single Scan produces both the Layout and the Appearance of a Room.
_Avoid_: capture (as a noun), import

**Layout**:
The measured shape of a Room: its walls, floor, and furniture, all at true dimensions.
_Avoid_: mesh, geometry, model

**Appearance**:
What a Room looks like, photorealistically, so that someone who has been in the real space recognizes it.
_Avoid_: texture, skin, splat, point cloud

**Board**:
The shared, interactive whiteboard in a Room. It sits exactly over a real writing surface (a whiteboard or chalkboard) at true size. A Room with no real writing surface gets one Board on a wall the Room Curator chooses.
_Avoid_: whiteboard (that's the physical object that was scanned), canvas

**Page**:
A named, separate drawing area that a Board can show, such as "Exam 2 review" or "Lab 4". A Board shows one Page at a time, and any Student in the Study Session can create Pages or switch which one is showing.
_Avoid_: board (for a Page), slide, tab, canvas

**Live Window**:
A live web page placed on a Page, such as a Claude or ChatGPT chat, which everyone in the Study Session can see and scroll. When nobody has it open, it shows a **preview**, the latest picture of the page, so the group can still see what's in it.
_Avoid_: embed, iframe, screen share, AI chat card

**Table**:
A group of seats in a Room's Layout. Students seated at the same Table hear each other clearly, wherever they sit around it.
_Avoid_: pod, group, cluster

**Desk Mode**:
The state of a Student who is seated in a Room but working in other apps, while still seeing the Room and hearing their Study Group.
_Avoid_: focus mode, away, AFK, background mode

**Laptop**:
The virtual laptop on the Table in front of a seated Student. It's only a signal, never a tool: **open** means the Student is in Desk Mode, working on their real computer; **closed** means they're seated and present.
_Avoid_: notes, editor, workspace, device

**Room View**:
A way of showing the Room during Desk Mode. The **pop-out** is a small always-on-top window, and it's the primary Room View because it carries voice. The **wallpaper** shows the Room on the desktop behind the Student's apps, and it's an optional extra.
_Avoid_: mini-player, widget, PiP, overlay

**Instructor**:
*(Future role, not in the MVP.)* A person who teaches a class from a fixed spot in a Room and controls its Boards.
_Avoid_: teacher, host, moderator

**Room Curator**:
A person allowed to publish Scans as Rooms. For now this is a small designated group. Later, any Student may become one.
_Avoid_: admin, scanner, creator

**Publish**:
To make a Scan available as a Room that Students can enter, after it passes review.
_Avoid_: upload, share, post

**Room Instance**:
One private copy of a Room, used by one Study Session. Every Room Instance of a Room has the same Layout, Appearance and Board positions. Each one shows only its own Study Group's people and Pages.
_Avoid_: copy, shard, server, lobby

**Study Group**:
A lasting group of Students who study together repeatedly. A Study Group owns its Pages, and has one Invite Link and a usual Room.
_Avoid_: team, party, squad, class

**Invite Link**:
The secret link that *is* membership of a Study Group in the MVP. Anyone who opens it joins that Study Group under a display name they type. There are no accounts. Any member present can reset it, and the old link stops working.
_Avoid_: room link, URL, code

**Study Session**:
One meeting of a Study Group in a Room.
_Avoid_: meeting, call, class

## Relationships

- The **Customer** provides the real spaces; each **Room** replicates exactly one of them
- A **Room** comes from one **Scan**, and has exactly one **Layout** and one **Appearance**, which line up with each other
- A **Study Group** has many **Study Sessions** over time. Each Study Session happens in its own **Room Instance** of exactly one **Room**
- Two Study Groups can use the same **Room** at the same moment, each in its own **Room Instance**, without seeing or hearing each other
- *(Beyond the MVP)* several Study Sessions may share one Room Instance of a big Room, at different **Tables**
- Opening a Study Group's **Invite Link** puts you in its current Study Session, in a Room Instance of its usual **Room**. At most 5 Students can be in one Study Session at once
- A **Study Group** owns its **Pages**. When the group meets again, its Pages come back to the Board, and another Study Group in the same Room sees only its own Pages
- A **Room** has one or more **Tables**. A seat belongs to at most one Table (a lone armchair belongs to none)
- A **Room** has one **Board** for each real writing surface in its **Layout**, or exactly one if there are none. The **Room Curator** places every Board
- A **Board** shows one **Page** at a time, and a Study Group can have any number of Pages
- A **Student** enters **Desk Mode** only while seated, and a Student in Desk Mode stays in the Study Session: they're heard and can hear
- A seated **Student**'s **Laptop** is open exactly while they're in **Desk Mode**, and everyone in the Study Session can see whether it's open
- Only a **Room Curator** can **Publish** a **Scan**. A **Student** who isn't a Room Curator can only enter Rooms that already exist

## Flagged ambiguities

- Not yet decided: whether a **Live Window** runs as a shared browser on a server (everyone can scroll) or streams one Student's own tab (only they can scroll). "Everyone can scroll" points to the shared browser.
- *Provisional:* "Desk Mode only while seated" is being tried out and may be reversed. The alternative is Desk Mode from anywhere, even while standing.
- A projector screen is not a **Board**. It will later become a place where a shared screen appears.
- "Accurately replicates" was resolved to mean both: a Room's **Layout** is dimensionally correct, *and* its **Appearance** is recognizable.
