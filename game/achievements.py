from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Achievement:
    achievement_id: int
    title: str
    description: str
    points: int


ACHIEVEMENTS = (
    Achievement(52318, "Reunited", "Help Flora find her missing husband", 5),
    Achievement(52319, "In Search of a Hero", "Complete Chapter 1", 10),
    Achievement(52320, "The Offering", "Bring peace to Tempe", 5),
    Achievement(52321, "Speak No Evil", "Restore the King's Voice", 5),
    Achievement(52322, "It's a Trap", "Collect the Iron Safe and leave", 5),
    Achievement(52323, "Making Friends", "Let the Healer slime join your party", 5),
    Achievement(52324, "Sneaking Out", "Find a way out of the Castle", 5),
    Achievement(52325, "The Kidnapped Imposter", "Rescue the fake princess", 5),
    Achievement(52326, "The Empty Castle", "Complete Chapter 2", 10),
    Achievement(52327, "The Architect", "Repair the bridge to Endor", 5),
    Achievement(52328, "Moving In", "Purchase the shop in Endor", 5),
    Achievement(52329, "The Traveling Merchant", "Complete Chapter 3", 10),
    Achievement(52330, "Edgar's Pupil", "Get Orin to join your party", 5),
    Achievement(52331, "Refugees", "Complete Chapter 4", 10),
    Achievement(52332, "Caravan", "Acquire the wagon", 10),
    Achievement(52333, "Starboard the Helm!", "Acquire the boat", 10),
    Achievement(52334, "Miracle Plant", "Help Cristo recover from his illness", 5),
    Achievement(52335, "Rematch", "Defeat Keeleon", 5),
    Achievement(52336, "You've Changed", "Defeat the evolved Balzack", 5),
    Achievement(52337, "Not So Funny", "Get the Zenithian Helm", 5),
    Achievement(52338, "Proof of Innocence", "Get the Zenithian Shield", 5),
    Achievement(52339, "Underwater Oasis", "Get the Zenithian Armor", 5),
    Achievement(52340, "A Monstrous Announcement", "Attend the conference at the Dire Palace", 5),
    Achievement(52341, "There's Gas Inside", "Acquire the hot air balloon", 10),
    Achievement(52342, "The Highest Branches", "Get the Zenithian Sword", 5),
    Achievement(52343, "Humans are Curious Creatures", "Talk to the Master Dragon", 5),
    Achievement(52344, "And Then There Were None", "Defeat the four guardians of the Dark World", 10),
    Achievement(52345, "Is This The End?", "Defeat Necrosaro", 25),
    Achievement(52346, "We Don't Need Another Hero", "Defeat Necrosaro without the hero in the party", 25),
    Achievement(52347, "Just the Two of Us", "Defeat Necrosaro with a party of two", 25),
    Achievement(52348, "High Roller", "Have at least 10,000 Casino coins", 5),
    Achievement(52349, "Tunnel Rat", "Be the 1000th person to use the new tunnel", 5),
    Achievement(52350, "Rosa's Fate", "Find out what happened to Rosa", 5),
    Achievement(52351, "Private Dance", "Try Pufpuf", 5),
    Achievement(52352, "Zenithia's Finest", "Doran joined the party", 5),
    Achievement(52353, "The One That Didn't Get Away", "Defeat a King Metal", 5),
    Achievement(52354, "Hidden Treasure - Great Lighthouse", "Find all three hidden treasures in the Great Lighthouse", 5),
    Achievement(52355, "Hidden Treasure - Endor", "Find the hidden treasure in Endor", 5),
    Achievement(52356, "Hidden Treasure - Gardenbur", "Find the hidden treasure in Gardenbur", 5),
    Achievement(52357, "Hidden Treasure - Shrine of the Horn", "Find the hidden treasure in the Shrine of the Horn", 5),
    Achievement(52358, "Hidden Treasure - Necrosaro's Palace", "Find the hidden treasure in Necrosaro's Palace", 5),
    Achievement(52359, "Arboreal Vandal", "Pluck a leaf from the World Tree", 5),
    Achievement(52360, "Small Medal Collector", "Find all 32 small medals", 50),
)

ACHIEVEMENTS_BY_ID = {
    achievement.achievement_id: achievement for achievement in ACHIEVEMENTS
}
TOTAL_POINTS = sum(achievement.points for achievement in ACHIEVEMENTS)