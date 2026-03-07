"""Tests for UK geographic classification."""

from app.workers.uk_geo import (
    classify_territory,
    is_city,
    is_national_park,
    classify_observations,
)


class TestClassifyTerritory:
    def test_london_is_england(self):
        assert classify_territory(51.5, -0.13) == "England"

    def test_edinburgh_is_scotland(self):
        assert classify_territory(55.95, -3.19) == "Scotland"

    def test_cardiff_is_wales(self):
        assert classify_territory(51.48, -3.18) == "Wales"

    def test_belfast_is_northern_ireland(self):
        assert classify_territory(54.60, -5.93) == "Northern Ireland"

    def test_offshore_returns_none(self):
        assert classify_territory(48.0, -5.0) is None

    def test_far_north_scotland(self):
        assert classify_territory(58.0, -3.0) == "Scotland"

    def test_snowdonia_area_is_wales(self):
        assert classify_territory(52.9, -3.9) == "Wales"

    def test_manchester_is_england(self):
        assert classify_territory(53.48, -2.24) == "England"


class TestIsCity:
    def test_london_centre(self):
        assert is_city(51.51, -0.13) is True

    def test_birmingham_centre(self):
        assert is_city(52.49, -1.89) is True

    def test_remote_countryside(self):
        assert is_city(54.5, -2.5) is False

    def test_just_outside_city_radius(self):
        # Well north of London, beyond 25km radius
        assert is_city(52.0, -0.13) is False


class TestIsNationalPark:
    def test_lake_district_centre(self):
        assert is_national_park(54.45, -3.1) is True

    def test_peak_district_centre(self):
        assert is_national_park(53.3, -1.8) is True

    def test_not_in_any_park(self):
        assert is_national_park(51.5, -0.13) is False

    def test_snowdonia(self):
        assert is_national_park(52.9, -3.9) is True

    def test_cairngorms(self):
        assert is_national_park(57.0, -3.6) is True


class TestClassifyObservations:
    def test_batch_classification(self):
        obs_data = {
            1: {"lat": 51.5, "lng": -0.13},     # London, England, city
            2: {"lat": 54.45, "lng": -3.1},      # Lake District, England, park
            3: {"lat": None, "lng": None},        # No coords
        }
        result = classify_observations(obs_data)

        assert result[1]["territory"] == "England"
        assert result[1]["is_city"] is True
        assert result[1]["is_national_park"] is False

        assert result[2]["territory"] == "England"
        assert result[2]["is_city"] is False
        assert result[2]["is_national_park"] is True

        assert result[3]["territory"] is None
        assert result[3]["is_city"] is False
        assert result[3]["is_national_park"] is False

    def test_empty_input(self):
        assert classify_observations({}) == {}
