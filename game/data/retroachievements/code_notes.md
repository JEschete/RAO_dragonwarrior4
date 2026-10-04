# RetroAchievements Code Notes

Imported from authenticated RetroAchievements code-notes pages.

Imported: 2026-09-08T14:33:15.935545+00:00

## RA Game 4612

Source: https://retroachievements.org/codenotes.php?g=4612

| Address | Scope | Author | Note |
| --- | --- | --- | --- |
| `0x000014` | set | Jamiras | buttons pressed |
| `0x000017` | set | Jamiras | [2byte] base poker winnings (before double-or-nothing) |
| `0x000028` | set | mickyt888 | map id? |
| `0x000029` | set | Jamiras | Slot 1 Position |
| `0x00002A` | set | Jamiras | Slot 2 Position |
| `0x00002B` | set | Jamiras | Slot 3 Position |
| `0x000036` | set | Jamiras | Slot rows lit |
| `0x000042` | set | Jamiras | Player World X |
| `0x000043` | set | Jamiras | Player World Y |
| `0x000044` | set | Jamiras | Player Town/Dungeon X |
| `0x000045` | set | Jamiras | Player Town/Dungeon Y |
| `0x000081` | set | Jamiras | Winning Poker hand type (0=Royal Flush...8=Two Pair, FF=nothing) |
| `0x0000C0` | set | macacocareca | 16bit (Monster Code?) |
| `0x0000FA` | set | mickyt888 | possible item code? |
| `0x0000FD` | set | Jamiras | Poker Double-or-Nothing index |
| `0x000302` | set | Jamiras | next character to write |
| `0x0003CF` | set | Jamiras | cursor position, high4=X, low4=Y |
| `0x000440` | set | macacocareca | (Monster 1 Code) |
| `0x000441` | set | macacocareca | (Monster 2 Code) |
| `0x000551` | set | Jamiras | text output X |
| `0x000552` | set | Jamiras | text output Y |
| `0x00058F` | set | Jamiras | Region indicator?<br>00=JP<br>10=US |
| `0x0006AA` | set | Jamiras | [194 bytes] dialogue window text (8 lines, 24 columns) |
| `0x00078B` | set | LordKuddy | Ragnar Inventory? |
| `0x006032` | set | macacocareca | Cristo Item Slot 1 |
| `0x00608C` | set | macacocareca | Brey Item Slot 1 |
| `0x0060B6` | set | mickyt888 | character 1 hp? |
| `0x0060BA` | set | mickyt888 | character 1's level |
| `0x0060BB` | set | mickyt888 | 1 strenth |
| `0x0060BC` | set | mickyt888 | 1 agility |
| `0x0060C1` | set | mickyt888 | max hp |
| `0x0060C5` | set | mickyt888 | exp points |
| `0x0060C8` | set | LordKuddy | Ragnar Inventory Slot 1 |
| `0x0060C9` | set | LordKuddy | Ragnar Inventory Slot 2 |
| `0x0060CA` | set | LordKuddy | Ragnar Inventory Slot 3 |
| `0x0060CB` | set | LordKuddy | Ragnar Inventory Slot 4 |
| `0x0060CC` | set | LordKuddy | Ragnar Inventory Slot 5 |
| `0x0060CD` | set | LordKuddy | Ragnar Inventory Slot 6 |
| `0x0060CE` | set | LordKuddy | Ragnar Inventory Slot 7 |
| `0x0060CF` | set | LordKuddy | Ragnar Inventory Slot 8 |
| `0x0060E6` | set | macacocareca | (Alenna Inventory 1) |
| `0x006157` | set | Jamiras | [24-bit] total Gold |
| `0x00615A` | set | Jamiras | Current Chapter (-1) |
| `0x00615C` | set | Jamiras | Hero gender |
| `0x00615D` | set | Jamiras | [8-bytes] hero name |
| `0x006165` | set | mickyt888 | event value? yes? no? |
| `0x00616A` | set | macacocareca | Character 1 |
| `0x00616B` | set | macacocareca | Character 2 |
| `0x00616C` | set | macacocareca | Character 3 |
| `0x00616D` | set | macacocareca | Character 4 |
| `0x0061DB` | set | Jamiras | Vault items |
| `0x00625D` | set | Jamiras | b0-3: chests in Burland Castle<br>b4-7: chests in Keeleon Castle |
| `0x006261` | set | Jamiras | b0: chest in Aktemto Mine, b1: chest in Desert Inn<br>b2: chest in Kievs, b3-5: chests in Lakanaba<br>b6-b7: chests in Esturk's Palace |
| `0x006262` | set | Jamiras | b0-5: chests in Esturk's Palace<br>b6-7: chests in Aktemto Mine |
| `0x006263` | set | Jamiras | b0-2: chests in Cave of Padequia<br>b3-5: chests in Shrine of Breaking Waves<br>b6-7: chests in Esturk's Palace |
| `0x006264` | set | Jamiras | b0-4: chests in Cave southeast of Gardenbur<br>b5-7: chests in Cave of Padequia |
| `0x006265` | set | Jamiras | b0: chest in Cave south of Frenor<br>b1-b6: chests in Cave west of Kievs<br>b7: chest in Cave southeast of Gardenbur |
| `0x006266` | set | Jamiras | b0: chest in Cascade Cave<br>b1-b3: chests in Secret Playground<br>b4-b7: chests in Cave south of Frenor |
| `0x006267` | set | Jamiras | b0-b3: chests in Cave to the Dark World<br>b4-b7: chests in Cascade Cave |
| `0x006268` | set | Jamiras | b0-b7: chests in Cave to the Dark World |
| `0x006269` | set | Jamiras | b0-b3: chests in Cave of Silver Statuette<br>b4: chest in Cave of Betrayal, b5-b6: chests in Cave north of Lakanaba<br>b7: chests in Cave to the Dark World |
| `0x00626A` | set | Jamiras | b0-1: chests in Cave of Izmit<br>b2-7: chests in Cave of Silver Statuette |
| `0x00626B` | set | Jamiras | b0-4: chests in Zenithian Tower<br>b5-7: chests in Royal Crypt |
| `0x00626C` | set | Jamiras | b0-1: chests in Loch Tower<br>b2-4: chests in World Tree<br>b5-7: chests in Birdsong Tower |
| `0x00626D` | set | Jamiras | b0-3: chests in Great Lighthouse<br>b4-7: chests in Loch Tower |
| `0x00626E` | set | Jamiras | b1: chest in Great Lighthouse<br>b2: chest in Konenber<br>b3-b4: chests in Great Lighthouse<br>b6-b7: chests in Great Lighthouse |
| `0x006270` | set | Jamiras | b0-4: chests in Shrine of the Colossus<br>b5-7: chests in Shrine of the Horn |
| `0x006275` | set | Jamiras | items hidden in furniture: Monbaraba, hero's hometown, Izmit, Haville, and Bazaar |
| `0x006276` | set | Jamiras | items hidden in furniture: Lakanaba, Kieves, Gottside, Konenber, Island Shack, Edgar's Lab, Secret Playground |
| `0x00627A` | set | Jamiras | Item received from chest/dresser/pot |
| `0x00627E` | set | Jamiras | b0: follow child at Loch Tower<br>b1-3,7: advance story for escape<br>b4: start chapter 1, b5-6: flora/alex |
| `0x006281` | set | Jamiras | b0-2: man in Cave to Izmit dialog indicator<br>b3-4: Tempe offering, b5: escape castle<br>b6: Healie in party, b7: find Alex |
| `0x006283` | set | mickyt888 | bit7=defeated 1st boss |
| `0x006284` | set | Jamiras | b0-3: ch3 story flags<br>b4-5: ch4 story flags<br>b6-7: ch2 story flags |
| `0x006286` | set | Jamiras | b0,2-7: ch3 story flags<br>b1: ch2 story flag |
| `0x006289` | set | Jamiras | b0-1,4-5: ch5 story flags<br>b2: ch2 story flag, b3,6: ch3 story flag<br>b7: patrolling guard sits at eatery |
| `0x00628E` | set | Jamiras | b0: get boat, b1: get balloon<br>b3: furniture in woodsmans hut<br>b2,4: ch5 story flags, b6-7: ch3 story flags |
| `0x00628F` | set | Jamiras | Taloon's consignment progress: low=swords, hi=armor |
| `0x006292` | set | Jamiras | Characters from earlier chapters that have joined with the hero |
| `0x006296` | set | Jamiras | Transform steps remaining |
| `0x006297` | set | Jamiras | Transform shape |
| `0x0062A2` | set | Jamiras | Small Medals turned in |
| `0x0062AD` | set | Jamiras | [3 bytes] Casino Coins |
| `0x0062E7` | set | Jamiras | [Taloon's Shop] Boomerangs in stock |
| `0x0062E8` | set | Jamiras | [Taloon's Shop] Chain Sickles in stock |
| `0x0062ED` | set | Jamiras | Time of Day |
| `0x006E7F` | set | Jamiras | Arena<br>b0-b2=predicted winner<br>b7=correct, b6=incorrect |
| `0x006E81` | set | Jamiras | Arena Round |
| `0x006E82` | set | Jamiras | Arena Bet |
| `0x006E83` | set | Jamiras | Arena payout |
| `0x007201` | set | Jamiras | [Battle] [2 bytes] Gold earned from defeated monsters |
| `0x007203` | set | Jamiras | [Battle] [3 bytes] Experience earned from defeated monsters |
| `0x007274` | set | Jamiras | Monster 1 agility |
| `0x007275` | set | Jamiras | Monster 1 attack |
| `0x007277` | set | Jamiras | Monster 1 defense |
| `0x00727A` | set | Jamiras | Monster 1 status |
| `0x00727E` | set | Jamiras | [2byte] Monster 1 HP |
| `0x007280` | set | Jamiras | Monster 1 MP |
| `0x007281` | set | Jamiras | Monster 1 group/letter |
| `0x007282` | set | Jamiras | Monster 2 agility |
| `0x007283` | set | Jamiras | Monster 2 attack |
| `0x007285` | set | Jamiras | Monster 2 defense |
| `0x007288` | set | Jamiras | Monster 2 status |
| `0x00728C` | set | Jamiras | [2byte] Monster 2 HP |
| `0x00728E` | set | Jamiras | Monster 2 MP |
| `0x00728F` | set | Jamiras | Monster 2 group/letter |
| `0x007290` | set | Jamiras | Monster 3 agility |
| `0x007291` | set | Jamiras | Monster 3 attack |
| `0x007293` | set | Jamiras | Monster 3 defense |
| `0x007296` | set | Jamiras | Monster 3 status |
| `0x00729A` | set | Jamiras | [2byte] Monster 3 HP |
| `0x00729D` | set | Jamiras | Monster 3 group/letter |
| `0x007600` | set | Jamiras | Poker Card 1 |
| `0x007601` | set | Jamiras | Poker Card 2 |
| `0x007602` | set | Jamiras | Poker Card 3 |
| `0x007603` | set | Jamiras | Poker Card 4 |
| `0x007604` | set | Jamiras | Poker Card 5 |
