"""Population-density raster sampling for impact-zone centroids."""
import logging
import math
from pathlib import Path

import rasterio
from rasterio.warp import transform

logger = logging.getLogger(__name__)


class PopulationDensityRaster:
    def __init__(self, raster_path: str | None):
        self.raster_path = raster_path
        self.dataset = None

    def __enter__(self):
        if self.raster_path:
            path = Path(self.raster_path)
            if path.is_file():
                try:
                    self.dataset = rasterio.open(path)
                except rasterio.errors.RasterioError as exc:
                    logger.warning("Could not open population raster %s: %s", path, exc)
            else:
                logger.warning("Population raster does not exist: %s", path)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.dataset is not None:
            self.dataset.close()
            self.dataset = None

    def sample(self, longitude: float, latitude: float) -> float | None:
        """Sample people/km² at a WGS84 coordinate; return None outside valid data."""
        dataset = self.dataset
        if dataset is None or dataset.crs is None:
            return None
        try:
            x_values, y_values = transform("EPSG:4326", dataset.crs, [longitude], [latitude])
            row, col = dataset.index(x_values[0], y_values[0])
            if row < 0 or col < 0 or row >= dataset.height or col >= dataset.width:
                return None
            value = float(dataset.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
            if not math.isfinite(value) or value < 0 or value == dataset.nodata:
                return None
            return value
        except (IndexError, TypeError, ValueError, rasterio.errors.RasterioError) as exc:
            logger.debug("Population raster sample failed: %s", exc)
            return None