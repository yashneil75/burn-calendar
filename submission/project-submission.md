# NASA Space Apps submission: Califire

## Project title

Califire

## High-level project summary

Califire turns NASA satellite fire detections into an interactive daily record of fire activity from 2000 to the present. MODIS and VIIRS have different resolutions and sensitivities, making their detections difficult to compare directly. Our experimental model estimates a MODIS-Aqua-like activity index from VIIRS observations, while earlier years use MODIS observations directly. A calendar, historical archive and map let users explore when and where activity was reported across California. The tool is designed for historical exploration—not fire prediction or emergency alerts—and makes sensor transitions and data limitations visible.

## Detailed project description

Fire activity is seasonal and varies dramatically from year to year, but satellite records change as instruments are launched and retired. Comparing raw hotspot counts across those sensors can confuse changes in observation with changes on the ground. We built Califire to make the record easier to explore in one place, while showing where comparisons remain uncertain.

The app uses NASA FIRMS MODIS and VIIRS active-fire detections. The historical calendar begins in November 2000 with MODIS observations; the VIIRS era begins in 2012. We filter detection centres to a Natural Earth California boundary, group observations into satellite passes, and count occupied one-kilometre equal-area grid cells. A California-region Poisson model estimates an Aqua-MODIS-like occupied-cell activity index from each S-NPP VIIRS pass. The daily index is the sum of pass estimates; earlier MODIS days use observed occupied cells. The model was trained on a California bounding-box cohort, so applying it to the state polygon is an approximation.

Users can explore a month day by day, open a day to see its activity, fire radiative power and day/night breakdown, compare months in the multi-year archive, and use the map to explore the geographic distribution. The map and calendar are rebuilt together as new FIRMS data arrive. Our selected area is California; the current app does not let users draw arbitrary regions.

The product is an exploratory index, not burned area, a count of distinct fires, a forecast, or an emergency alert. Missing days do not mean zero fire: clouds, sensor coverage and observation timing can hide activity. MODIS and VIIRS observe differently, the historical model has meaningful year-to-year error, and NOAA-20 estimates after the S-NPP transition are provisional because a sensor-specific correction has not been validated. These limitations are documented on the methods page.

## Links

- Final project: https://yashneil75.github.io/califire/
- Source code: https://github.com/yashneil75/califire
- Methods and validation: https://yashneil75.github.io/califire/methodology.html
- Demo: upload `Califire-Demo.pdf` or `Califire-Demo.pptx` and paste a publicly accessible link here.

## NASA data and other resources

- **NASA FIRMS**, Fire Information for Resource Management System: https://www.earthdata.nasa.gov/data/tools/firms — MODIS and VIIRS active-fire detections, including standard-processing and near-real-time products.
- **NASA FIRMS Area API:** https://firms.modaps.eosdis.nasa.gov/api/area/ — recent detection data for the daily refresh.
- **Source Cooperative FIRMS mirror:** https://source.coop/portolan-mirrors/firms-catalog — historical NASA FIRMS detections used for the archive rebuild.
- **Natural Earth:** https://www.naturalearthdata.com/ — California boundary used to filter detection centres and display the map.
- **NASA VIIRS 375 m Active Fire Product User Guide:** https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf — sensor products and interpretation.
- **Tools:** Python, NumPy, Shapely, DuckDB, JavaScript, Leaflet, GitHub Actions and GitHub Pages.

NASA acknowledgment: We acknowledge the use of data from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's Earth Observing System Data and Information System (EOSDIS).

## AI-use disclosure

We used OpenAI Codex, Claude Code and OpenCode as AI-assisted development tools during the project. They helped with research, coding, debugging and/or documentation. OpenAI Codex also assisted with testing and preparation of these submission materials. The team is responsible for reviewing the output, making project decisions, and verifying the final submission.

## Before submitting

- Confirm the AI-use description accurately reflects how each tool was used.
- Upload the slide deck to a publicly accessible location and paste its link into the Project Demo field. Check the link in a private browser window.
- Submit the project in the Space Apps team page's Project tab and complete the required terms acknowledgment.
