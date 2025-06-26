# arg-inundaciones
Mapeo automarizado de inundaciones en Argentina con imagenes Sentinel 1 y 2

## Setup
Install the repo using `git clone`. Navigate to the root directory and install the virutal environment and dependencies using `uv sync`. Once that's done, run `uv run pre-commit install` in the root directory to set up the precommit hooks (configured in `.pre-commit-config.yaml`).

Run the main script with `uv run main.py`.

## Data Sources

Gaul L1: https://data.apps.fao.org/catalog/iso/34f97afc-6218-459a-971d-5af1162d318a
Gaul L2: https://data.apps.fao.org/catalog/dataset/60b23906-f21a-49ef-8424-f3645e70264e

## Roadmap

So, for work with Andrea:

- First need to identify avaiable images
    - Criteria are: S1 or S2 images within 2 days of a flood event
    - We need to confirm that EITHER S1 images are available OR the S2 images have a low cloud cover percentage
    - We need to be able tag the images by cloud cover, completeness, proximity to the event in question, and the type of flood in question
- We need an efficient way of filtering for the region of the flood in question—we don’t want to be querying for ALL of Argentina
- Need to use STAC index for this
    - How do we do our spatial filters?
    - Make sure to maximize the efficiency of the query by working with the most parsimonious bounding box possible
    - Only need to return metadata—not the images themselves yet

Then what am I going to need to do with these? Efficiently query them and apply some kind of algorithm to them. Do I want them locally? Probably not. And I will want them in COG format that can easily be opened in QGIS, but also can be shared easily.

Codebase needs to be documented, replicable, include unit testing, integration tests, API tests. 

QUestions to resolve:

- How do we incorporate the models for better pixel ID? Which models do we use? How do we identify a “good” flood mask? How do we account for clouds in the imagery? How do we effectively spatially filter the assets? (This might come down to how the EMDAT database is structured).

Getting efficient spatial filtering down *first* is important, I think.

What is the raison d’etre here? Basically, that it’s easy to just run automated algorithms here, but we want to make it easier to produce a handful of high-quality masks. So, we start by using the stac index to filter only for likely high quality images, we then apply initial pre-processing, and we give the option of different algorithms to improve the imagery. As a final step, we make it easy to hand-correct the imagery.

We also need to flag caveats, known issues, etc., and document the existing research. What are examples that I’m building this on?

Add a license, obviously, a readme, a setup guide. It’s basically an ETL pipeline.

Where do data get stored? Presumably in the cloud, although local storag emight actually be preferrable for easy manipulation…?

COG format is ideal for data storage + viz (as opposed to zarr). We can use xarray for efficient loading of COG data.