"""iNaturalist API constants."""

API_BASE = "https://api.inaturalist.org/v1"
UK_PLACE_ID = 6857

# Annotation attribute IDs on iNaturalist
# These are the standard annotation attributes used globally
ANNOTATION_PLANT_PHENOLOGY = 12  # "Plant Phenology"
ANNOTATION_LIFE_STAGE = 1  # "Life Stage"

# Plant Phenology values
PHENOLOGY_FLOWERING = 13
PHENOLOGY_FRUITING = 14
PHENOLOGY_BUDDING = 15

# Life Stage values (for plants: relevant annotations)
LIFE_STAGE_ADULT = 2

# Commonly used annotation labels for display
ANNOTATION_LABELS = {
    12: "Plant Phenology",
    1: "Life Stage",
}

PHENOLOGY_LABELS = {
    13: "Flowering",
    14: "Fruiting",
    15: "Budding",
}
