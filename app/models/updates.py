from pydantic import BaseModel, Field
from typing import Optional, List, Annotated, Literal
from enum import Enum

class Categories(str, Enum):
    # News & Current Affairs
    politics = "politics"
    government = "government"
    law = "law"
    news = "news"
    world = "world"
    local = "local"
    crime = "crime"
    weather = "weather"
    disaster = "disaster"

    # Business & Economy
    business = "business"
    finance = "finance"
    investing = "investing"
    crypto = "crypto"
    markets = "markets"
    startups = "startups"
    economy = "economy"
    real_estate = "real_estate"
    jobs = "jobs"
    career = "career"

    # Tech & Science
    technology = "technology"
    gadgets = "gadgets"
    ai = "ai"
    software = "software"
    cybersecurity = "cybersecurity"
    science = "science"
    space = "space"
    environment = "environment"
    climate = "climate"

    # Health & Lifestyle
    health = "health"
    medicine = "medicine"
    nutrition = "nutrition"
    fitness = "fitness"
    wellness = "wellness"
    mental_health = "mental_health"
    parenting = "parenting"
    relationships = "relationships"
    lifestyle = "lifestyle"

    # Education & Learning
    education = "education"
    academic = "academic"
    learning = "learning"
    books = "books"
    languages = "languages"
    study = "study"
    

    # Entertainment & Culture
    entertainment = "entertainment"
    movies = "movies"
    tv = "tv"
    music = "music"
    art = "art"
    theater = "theater"
    celebrity = "celebrity"
    pop_culture = "pop_culture"

    # Sports
    sports = "sports"
    football = "football"
    basketball = "basketball"
    soccer = "soccer"
    tennis = "tennis"
    motorsports = "motorsports"
    esports = "esports"
    gaming = "gaming"

    # Other Interests
    travel = "travel"
    food = "food"
    cooking = "cooking"
    drinks = "drinks"
    fashion = "fashion"
    beauty = "beauty"
    home_garden = "home_garden"
    diy = "diy"
    automotive = "automotive"
    pets = "pets"
    animals = "animals"
    hobbies = "hobbies"
    photography = "photography"

    # Society
    religion = "religion"
    spirituality = "spirituality"
    social = "social"
    community = "community"
    activism = "activism"
    history = "history"


class Annotations(BaseModel):
    category: Categories
    score: float
    

class Subcategory(BaseModel):
    name: str
    intensity_percent: int = Field(ge=0, le=100)


class Flag(BaseModel):
    name: str
    intensity_percent: int = Field(ge=0, le=100)
    severity_percent: int = Field(ge=0, le=100)
    subcategories: List[Subcategory]


class ContentContext(BaseModel):
    stance: Literal[
        "endorsed",
        "quoted",
        "condemned",
        "educational",
        "fictional",
        "descriptive",
        "unclear"
    ]


class ContentSafetyAnnotation(BaseModel):
    schema_version: Literal["1.0"]
    flags: List[Flag]
    context: ContentContext

class SentAnnotations(BaseModel):
    update_id: str
    user_id:str
    category: Categories # the chosen category that should be swapped to
    annotations: List[Annotations] 
    safety: ContentSafetyAnnotation


class AcknowledgeUpdate(BaseModel):
    update_id: str = Field(..., max_length=40)


# So updates are public, private updates are simply messages sent to everyone on
# updates list while global updates are not encrypted
class Media(BaseModel):
    media_url: str  = Field(..., description="The URL of the media", max_length=400)
    media_type: str  = Field(..., description="The type of the media", max_length=10)
    media_description: str  = Field(..., description="The description of the media", max_length=300)


class updatesModel(BaseModel):
    nickname: str = Field(..., max_length=15, description="The name of the poster")
    media: Optional[Media] = Field(None, description="The media of the update")
    text: str = Field(..., max_length=10000, description="Not encrypted")
    category: Categories
    hashtag: str = Field(..., max_length=100, description="This is a tag that is used to deeply root the categories")


class RequestUpdates(BaseModel):
    user_ids: Optional[List[str]] = Field(None, description="The user IDs to retrieve updates for, this is for people who want to see updates from specific people only and not everyone", max_length=100)
    category: Optional[Categories] = Field(None, description="A single category to filter by")
    categories: Optional[List[Categories]] = Field(None, max_length=50, description="Multiple categories to filter by (used by the feed-control preferences). Omit all filters to get every update.")
    hashtags: Optional[List[Annotated[str, Field(max_length=20)]]] = Field(None, max_length = 10)
    before: Optional[int] = Field(default=0, description="The timestamp before which to retrieve updates", le = 500)
    limit: int = Field(default=20, le=500)


# Return a list of hashtags that are available or trending.
class ReturnListAvailable(BaseModel):
    hashtags: List[str] = Field(..., max_length=50, description="The list of hashtags")


class MarkUpdateRead(BaseModel):
    update_id: str = Field(..., max_length=40)
    like: bool = Field(False, description="If the update has been liked")
    follow: bool = Field(False, description="If the updater has been followed")
    dislike: bool = Field(False, description="If the update has been disliked")
    unfollow: bool = Field(False, description="If the updater has been unfollowed")


class UpdatesResponse(BaseModel):
    update_id: str
    user_id: str
    nickname: Optional[str] = Field(None, description="The name of the poster")
    text: str = Field(..., description="Not encrypted text", max_length=10000)
    expires: int
    media: Optional[Media] = Field(None, description="If the update is media, it is in here")
    annotations: Optional[List[Annotations]] = None
    safety: Optional[ContentSafetyAnnotation] = None
    annotated: bool = False



class UpdateProgress(BaseModel):
    update_id: str
    views: int
    likes: int
    follows: int
    dislikes: int


class Comment(BaseModel):
    update_id: str  = Field(..., max_length=40)
    reply_to: Optional[str] = Field(None, description="This is if the comment is a reply to another comment", max_length=40)  
    at_user: Optional[str] = Field(None, description="This is if the comment is a reply to another comment", max_length=100) 
    nickname: Optional[str] = Field(None, description="The name of the poster", max_length=40) 
    text: str = Field(..., description="Not encrypted text")  


class CommentResponse(BaseModel):
    update_id: str
    comment_id: str
    user_id: str
    nickname: Optional[str] = Field(None, description="The name of the poster")
    text: str = Field(..., description="Not encrypted text")


# Now what happens is that if people keep commenting on a post the time of
# expiration of that post keeps being extended. Else it dies off. This is to
# protect the db from bloating.
class AllComments(BaseModel):
    update_id: str
    comments: List[CommentResponse]



sub_cat= [
  {
    "politics": [
      "political-parties",
      "elections",
      "political-ideologies",
      "political-campaigns",
      "political-debates",
      "political-leaders",
      "international-relations",
      "political-movements"
    ]
  },
  {
    "government": [
      "public-policy",
      "public-services",
      "governance",
      "public-administration",
      "government-spending",
      "corruption",
      "public-sector",
      "government-reforms"
    ]
  },
  {
    "law": [
      "constitutional-law",
      "criminal-law",
      "civil-law",
      "human-rights-law",
      "business-law",
      "family-law",
      "legal-reforms",
      "court-cases"
    ]
  },
  {
    "news": [
      "breaking-news",
      "investigative-journalism",
      "political-news",
      "business-news",
      "technology-news",
      "health-news",
      "sports-news",
      "human-interest"
    ]
  },
  {
    "world": [
      "international-news",
      "global-conflicts",
      "diplomacy",
      "international-organizations",
      "foreign-policy",
      "global-economy",
      "migration",
      "international-development"
    ]
  },
  {
    "local": [
      "local-government",
      "community-news",
      "local-business",
      "local-politics",
      "transportation",
      "public-infrastructure",
      "neighbourhood-issues",
      "local-events"
    ]
  },
  {
    "crime": [
      "violent-crime",
      "cybercrime",
      "fraud-and-scams",
      "organized-crime",
      "theft-and-robbery",
      "police-investigations",
      "criminal-justice",
      "public-safety"
    ]
  },
  {
    "weather": [
      "weather-forecasts",
      "rainfall",
      "storms",
      "heatwaves",
      "flood-warnings",
      "drought",
      "seasonal-weather",
      "weather-patterns"
    ]
  },
  {
    "disaster": [
      "natural-disasters",
      "flooding",
      "earthquakes",
      "wildfires",
      "industrial-accidents",
      "emergency-response",
      "humanitarian-crises",
      "disaster-recovery"
    ]
  },
  {
    "business": [
      "small-business",
      "business-management",
      "business-strategy",
      "sales-and-marketing",
      "customer-service",
      "business-operations",
      "business-models",
      "business-growth"
    ]
  },
  {
    "finance": [
      "personal-finance",
      "banking",
      "loans-and-credit",
      "budgeting",
      "taxation",
      "insurance",
      "financial-planning",
      "financial-literacy"
    ]
  },
  {
    "investing": [
      "stock-investing",
      "bond-investing",
      "dividend-investing",
      "value-investing",
      "growth-investing",
      "index-funds",
      "portfolio-management",
      "investment-strategy"
    ]
  },
  {
    "crypto": [
      "cryptocurrencies",
      "bitcoin",
      "ethereum",
      "blockchain",
      "decentralized-finance",
      "crypto-trading",
      "crypto-regulation",
      "web3"
    ]
  },
  {
    "markets": [
      "stock-market",
      "forex-market",
      "commodity-market",
      "bond-market",
      "market-analysis",
      "market-trends",
      "market-volatility",
      "market-regulation"
    ]
  },
  {
    "startups": [
      "startup-funding",
      "venture-capital",
      "bootstrapping",
      "startup-ideas",
      "product-market-fit",
      "business-pitching",
      "startup-founders",
      "startup-growth"
    ]
  },
  {
    "economy": [
      "inflation",
      "economic-growth",
      "recession",
      "unemployment",
      "monetary-policy",
      "fiscal-policy",
      "international-trade",
      "economic-inequality"
    ]
  },
  {
    "real_estate": [
      "residential-property",
      "commercial-property",
      "property-investment",
      "renting",
      "home-buying",
      "property-development",
      "property-management",
      "real-estate-market"
    ]
  },
  {
    "jobs": [
      "job-openings",
      "remote-jobs",
      "freelancing",
      "internships",
      "recruitment",
      "employment-trends",
      "workplace-rights",
      "salary-and-benefits"
    ]
  },
  {
    "career": [
      "career-planning",
      "professional-development",
      "career-change",
      "leadership",
      "workplace-skills",
      "networking",
      "interview-preparation",
      "work-life-balance"
    ]
  },
  {
    "technology": [
      "emerging-technology",
      "tech-industry",
      "digital-transformation",
      "internet-technology",
      "cloud-computing",
      "open-source",
      "technology-trends",
      "tech-ethics"
    ]
  },
  {
    "gadgets": [
      "smartphones",
      "laptops",
      "tablets",
      "wearables",
      "smart-home-devices",
      "audio-devices",
      "consumer-electronics",
      "gadget-reviews"
    ]
  },
  {
    "ai": [
      "machine-learning",
      "generative-ai",
      "large-language-models",
      "computer-vision",
      "natural-language-processing",
      "robotics",
      "ai-tools",
      "ai-ethics"
    ]
  },
  {
    "software": [
      "software-development",
      "web-development",
      "mobile-development",
      "desktop-applications",
      "databases",
      "programming-languages",
      "software-testing",
      "developer-tools"
    ]
  },
  {
    "cybersecurity": [
      "network-security",
      "application-security",
      "data-privacy",
      "ethical-hacking",
      "digital-forensics",
      "identity-and-access",
      "security-vulnerabilities",
      "cyber-threats"
    ]
  },
  {
    "science": [
      "biology",
      "chemistry",
      "physics",
      "mathematics",
      "neuroscience",
      "scientific-discoveries",
      "scientific-research",
      "scientific-method"
    ]
  },
  {
    "space": [
      "astronomy",
      "astrophysics",
      "space-exploration",
      "space-missions",
      "satellites",
      "rockets",
      "planetary-science",
      "extraterrestrial-life"
    ]
  },
  {
    "environment": [
      "biodiversity",
      "conservation",
      "pollution",
      "deforestation",
      "waste-management",
      "renewable-energy",
      "environmental-policy",
      "ecosystems"
    ]
  },
  {
    "climate": [
      "climate-change",
      "global-warming",
      "carbon-emissions",
      "climate-policy",
      "climate-adaptation",
      "climate-mitigation",
      "extreme-weather",
      "climate-science"
    ]
  },
  {
    "health": [
      "public-health",
      "healthcare-access",
      "preventive-health",
      "chronic-conditions",
      "infectious-diseases",
      "health-policy",
      "health-research",
      "health-education"
    ]
  },
  {
    "medicine": [
      "medical-treatments",
      "medical-diagnosis",
      "pharmaceuticals",
      "surgery",
      "medical-research",
      "medical-technology",
      "clinical-trials",
      "healthcare-professionals"
    ]
  },
  {
    "nutrition": [
      "healthy-eating",
      "balanced-diets",
      "vitamins-and-minerals",
      "food-labels",
      "dietary-patterns",
      "food-safety",
      "weight-management",
      "nutrition-science"
    ]
  },
  {
    "fitness": [
      "strength-training",
      "cardio",
      "weightlifting",
      "running",
      "mobility-and-flexibility",
      "exercise-programs",
      "sports-conditioning",
      "fitness-equipment"
    ]
  },
  {
    "wellness": [
      "sleep",
      "stress-management",
      "self-care",
      "healthy-habits",
      "relaxation",
      "mindfulness",
      "holistic-wellness",
      "healthy-aging"
    ]
  },
  {
    "mental_health": [
      "anxiety",
      "depression",
      "emotional-wellbeing",
      "therapy",
      "psychology",
      "stress-and-burnout",
      "mental-health-awareness",
      "coping-strategies"
    ]
  },
  {
    "parenting": [
      "pregnancy-and-birth",
      "newborn-care",
      "child-development",
      "parenting-styles",
      "child-discipline",
      "parenting-teens",
      "family-routines",
      "parenting-challenges"
    ]
  },
  {
    "relationships": [
      "romantic-relationships",
      "marriage",
      "friendship",
      "family-relationships",
      "communication",
      "conflict-resolution",
      "dating",
      "relationship-advice"
    ]
  },
  {
    "lifestyle": [
      "daily-routines",
      "personal-growth",
      "minimalism",
      "productivity",
      "work-life-balance",
      "life-advice",
      "habits",
      "personal-organization"
    ]
  },
  {
    "education": [
      "primary-education",
      "secondary-education",
      "higher-education",
      "vocational-education",
      "online-education",
      "educational-policy",
      "school-administration",
      "educational-technology"
    ]
  },
  {
    "academic": [
      "academic-research",
      "research-methods",
      "academic-writing",
      "theses-and-dissertations",
      "peer-review",
      "scholarly-publications",
      "academic-conferences",
      "research-ethics"
    ]
  },
  {
    "learning": [
      "self-directed-learning",
      "skill-development",
      "experiential-learning",
      "online-learning",
      "learning-strategies",
      "memory-and-retention",
      "critical-thinking",
      "lifelong-learning"
    ]
  },
  {
    "books": [
      "fiction",
      "nonfiction",
      "literary-fiction",
      "science-fiction",
      "fantasy",
      "biographies",
      "book-reviews",
      "reading-recommendations"
    ]
  },
  {
    "languages": [
      "language-learning",
      "linguistics",
      "translation",
      "grammar",
      "vocabulary",
      "pronunciation",
      "multilingualism",
      "language-preservation"
    ]
  },
  {
    "study": [
      "study-techniques",
      "exam-preparation",
      "note-taking",
      "revision",
      "study-planning",
      "concentration",
      "student-life",
      "study-resources"
    ]
  },
  {
    "entertainment": [
      "entertainment-news",
      "entertainment-reviews",
      "live-entertainment",
      "variety-shows",
      "comedy",
      "reality-tv",
      "entertainment-industry",
      "upcoming-releases"
    ]
  },
  {
    "movies": [
      "action-movies",
      "comedy-movies",
      "drama-movies",
      "horror-movies",
      "science-fiction-movies",
      "animated-movies",
      "documentaries",
      "movie-reviews"
    ]
  },
  {
    "tv": [
      "tv-series",
      "sitcoms",
      "crime-dramas",
      "reality-shows",
      "tv-documentaries",
      "streaming-services",
      "tv-reviews",
      "show-recommendations"
    ]
  },
  {
    "music": [
      "pop-music",
      "hip-hop",
      "afrobeats",
      "gospel-music",
      "rock-music",
      "classical-music",
      "music-production",
      "music-reviews"
    ]
  },
  {
    "art": [
      "visual-art",
      "painting",
      "drawing",
      "sculpture",
      "digital-art",
      "illustration",
      "art-history",
      "art-exhibitions"
    ]
  },
  {
    "theater": [
      "stage-plays",
      "musical-theater",
      "acting",
      "playwriting",
      "stage-production",
      "directing",
      "theater-reviews",
      "performing-arts"
    ]
  },
  {
    "celebrity": [
      "celebrity-news",
      "celebrity-interviews",
      "celebrity-lifestyles",
      "celebrity-relationships",
      "celebrity-careers",
      "celebrity-controversies",
      "celebrity-fashion",
      "celebrity-interviews-and-profiles"
    ]
  },
  {
    "pop_culture": [
      "internet-culture",
      "memes",
      "viral-trends",
      "fandoms",
      "fan-theories",
      "internet-personalities",
      "cultural-trends",
      "nostalgia"
    ]
  },
  {
    "sports": [
      "sports-news",
      "sports-analysis",
      "sports-business",
      "sports-history",
      "sports-training",
      "sports-events",
      "athlete-profiles",
      "sports-rules"
    ]
  },
  {
    "football": [
      "football-news",
      "football-leagues",
      "football-clubs",
      "football-tactics",
      "football-transfers",
      "football-coaching",
      "football-players",
      "football-tournaments"
    ]
  },
  {
    "basketball": [
      "basketball-news",
      "basketball-leagues",
      "basketball-teams",
      "basketball-tactics",
      "basketball-training",
      "basketball-players",
      "basketball-tournaments",
      "basketball-analysis"
    ]
  },
  {
    "soccer": [
      "soccer-news",
      "international-soccer",
      "club-soccer",
      "soccer-tactics",
      "soccer-transfers",
      "soccer-coaching",
      "soccer-players",
      "soccer-tournaments"
    ]
  },
  {
    "tennis": [
      "tennis-news",
      "professional-tennis",
      "tennis-tournaments",
      "tennis-techniques",
      "tennis-training",
      "tennis-equipment",
      "tennis-players",
      "tennis-analysis"
    ]
  },
  {
    "motorsports": [
      "formula-one",
      "motorcycle-racing",
      "rally-racing",
      "endurance-racing",
      "motorsport-teams",
      "racing-drivers",
      "vehicle-performance",
      "motorsport-news"
    ]
  },
  {
    "esports": [
      "esports-tournaments",
      "professional-gaming",
      "esports-teams",
      "competitive-strategy",
      "esports-training",
      "gaming-streamers",
      "esports-industry",
      "esports-news"
    ]
  },
  {
    "gaming": [
      "pc-gaming",
      "console-gaming",
      "mobile-gaming",
      "game-reviews",
      "game-development",
      "role-playing-games",
      "strategy-games",
      "gaming-hardware"
    ]
  },
  {
    "travel": [
      "travel-destinations",
      "budget-travel",
      "luxury-travel",
      "solo-travel",
      "family-travel",
      "travel-planning",
      "cultural-tourism",
      "travel-safety"
    ]
  },
  {
    "food": [
      "food-culture",
      "restaurant-reviews",
      "street-food",
      "traditional-cuisine",
      "international-cuisine",
      "food-trends",
      "food-business",
      "food-safety"
    ]
  },
  {
    "cooking": [
      "home-cooking",
      "baking",
      "meal-preparation",
      "quick-recipes",
      "traditional-recipes",
      "cooking-techniques",
      "vegetarian-cooking",
      "kitchen-skills"
    ]
  },
  {
    "drinks": [
      "coffee",
      "tea",
      "smoothies",
      "juices",
      "non-alcoholic-drinks",
      "drink-recipes",
      "beverage-culture",
      "coffee-and-tea-brewing"
    ]
  },
  {
    "fashion": [
      "streetwear",
      "menswear",
      "womenswear",
      "traditional-fashion",
      "fashion-trends",
      "fashion-design",
      "clothing-brands",
      "personal-style"
    ]
  },
  {
    "beauty": [
      "skincare",
      "haircare",
      "makeup",
      "nail-care",
      "beauty-products",
      "beauty-tutorials",
      "fragrance",
      "beauty-trends"
    ]
  },
  {
    "home_garden": [
      "interior-design",
      "home-decor",
      "gardening",
      "houseplants",
      "landscaping",
      "home-organization",
      "home-maintenance",
      "small-space-living"
    ]
  },
  {
    "diy": [
      "home-repairs",
      "woodworking",
      "crafts",
      "upcycling",
      "sewing",
      "handmade-projects",
      "tool-guides",
      "diy-tutorials"
    ]
  },
  {
    "automotive": [
      "car-reviews",
      "vehicle-maintenance",
      "car-repair",
      "electric-vehicles",
      "motorcycles",
      "automotive-technology",
      "road-safety",
      "vehicle-buying"
    ]
  },
  {
    "pets": [
      "dog-care",
      "cat-care",
      "pet-training",
      "pet-health",
      "pet-nutrition",
      "pet-adoption",
      "pet-behaviour",
      "pet-products"
    ]
  },
  {
    "animals": [
      "wildlife",
      "animal-behaviour",
      "animal-conservation",
      "marine-life",
      "birds",
      "insects",
      "animal-science",
      "animal-welfare"
    ]
  },
  {
    "hobbies": [
      "collecting",
      "model-building",
      "board-games",
      "chess",
      "crafting",
      "outdoor-recreation",
      "gardening-hobbies",
      "leisure-activities"
    ]
  },
  {
    "photography": [
      "portrait-photography",
      "landscape-photography",
      "street-photography",
      "wildlife-photography",
      "mobile-photography",
      "photo-editing",
      "camera-equipment",
      "photography-techniques"
    ]
  },
  {
    "religion": [
      "christianity",
      "islam",
      "judaism",
      "hinduism",
      "buddhism",
      "traditional-religions",
      "religious-practices",
      "interfaith-dialogue"
    ]
  },
  {
    "spirituality": [
      "meditation",
      "mindfulness",
      "personal-growth",
      "spiritual-practices",
      "philosophy-of-life",
      "metaphysical-beliefs",
      "spiritual-experiences",
      "self-discovery"
    ]
  },
  {
    "social": [
      "social-issues",
      "social-norms",
      "human-behaviour",
      "family-and-society",
      "social-class",
      "identity-and-society",
      "social-change",
      "public-discourse"
    ]
  },
  {
    "community": [
      "local-community",
      "volunteering",
      "community-development",
      "mutual-aid",
      "cultural-communities",
      "online-communities",
      "community-services",
      "community-events"
    ]
  },
  {
    "activism": [
      "human-rights",
      "environmental-activism",
      "social-justice",
      "political-activism",
      "community-advocacy",
      "labour-activism",
      "protest-movements",
      "digital-campaigning"
    ]
  },
  {
    "history": [
      "ancient-history",
      "african-history",
      "nigerian-history",
      "world-history",
      "political-history",
      "cultural-history",
      "social-history",
      "historical-research"
    ]
  }
]
