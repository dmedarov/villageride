// static/js/map.js
document.addEventListener("DOMContentLoaded", () => {
  try {
    const mapEl = document.getElementById("map");
    // Ако няма контейнер или Leaflet не е зареден – излизаме тихо
    if (!mapEl || !window.L) {
      console.warn("VillageRide: map element or Leaflet not available.");
      return;
    }

    // ---- БАЗОВА КАРТА ----
    // Център по подразбиране – около Осойца (ориентировъчни координати)
    const DEFAULT_CENTER = [42.78, 23.78];
    const DEFAULT_ZOOM = 12;

    const map = L.map(mapEl).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> участници',
    }).addTo(map);

    const rides = Array.isArray(window.ridesData) ? window.ridesData : [];
    const requests = Array.isArray(window.requestsData) ? window.requestsData : [];

    const ridesLayer = L.layerGroup().addTo(map);
    const requestsLayer = L.layerGroup().addTo(map);

    const bounds = L.latLngBounds([]);

    // ---- ПРЕВОЗИ (шофьори) ----
    const rideTypeColors = {
      work: "#2563eb", // Работа
      school: "#16a34a", // Училище
      healthcare: "#dc2626", // Здраве
      other: "#6b7280", // Друго
    };

    rides.forEach((r) => {
      if (
        r.from_lat == null ||
        r.from_lng == null ||
        r.to_lat == null ||
        r.to_lng == null
      ) {
        return;
      }

      const from = L.latLng(r.from_lat, r.from_lng);
      const to = L.latLng(r.to_lat, r.to_lng);

      const color = rideTypeColors[r.ride_type] || "#6b7280";

      const line = L.polyline([from, to], {
        color: color,
        weight: 4,
        opacity: 0.8,
      }).addTo(ridesLayer);

      const popupHtml = `
        <strong>${r.driver || "Шофьор"}</strong><br/>
        ${r.from_location || "От"} → ${r.to_location || "До"}<br/>
        ${r.date || ""} ${r.time || ""}<br/>
        Тип: ${r.ride_type_label || ""}<br/>
        ${
          r.phone
            ? `<a href="tel:${r.phone}">📞 ${r.phone}</a>`
            : ""
        }
      `;

      line.bindPopup(popupHtml);

      bounds.extend(from);
      bounds.extend(to);
    });

    // ---- ЗАЯВКИ „Търся превоз“ (пътници) ----
    requests.forEach((req) => {
      if (req.from_lat == null || req.from_lng == null) {
        return;
      }

      const from = L.latLng(req.from_lat, req.from_lng);
      const marker = L.circleMarker(from, {
        radius: 7,
        color: "#ca8a04", // жълтеникаво – "търсен превоз"
        fillOpacity: 0.9,
      }).addTo(requestsLayer);

      const popupHtml = `
        <strong>${req.passenger || "Пътник"}</strong><br/>
        ${req.from_location || "От"} → ${req.to_location || "До"}<br/>
        ${req.date || ""} ${req.time || ""} (${req.time_flex_label || ""})<br/>
        Хора: ${req.people_count || ""}<br/>
        ${req.note ? `<em>${req.note}</em><br/>` : ""}
        ${
          req.phone
            ? `<a href="tel:${req.phone}">📞 ${req.phone}</a>`
            : ""
        }
      `;

      marker.bindPopup(popupHtml);
      bounds.extend(from);
    });

    // Ако има данни – fitBounds, иначе оставаме на DEFAULT_CENTER
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [24, 24] });
    }

    // ---- РЕЖИМИ „От“ / „До“ и клик по картата ----
    let currentMode = "from";

    const fromBtn = document.querySelector('[data-map-mode="from"]');
    const toBtn = document.querySelector('[data-map-mode="to"]');

    const updateModeUi = () => {
      [fromBtn, toBtn].forEach((btn) => {
        if (!btn) return;
        const mode = btn.getAttribute("data-map-mode");
        if (mode === currentMode) {
          btn.classList.add("pill-active");
        } else {
          btn.classList.remove("pill-active");
        }
      });
    };

    if (fromBtn) {
      fromBtn.addEventListener("click", () => {
        currentMode = "from";
        updateModeUi();
      });
    }
    if (toBtn) {
      toBtn.addEventListener("click", () => {
        currentMode = "to";
        updateModeUi();
      });
    }
    updateModeUi();

    // Полета за попълване – ако някое липсва, просто го прескачаме
    const offerFromField = document.querySelector("#offer-from");
    const offerToField = document.querySelector("#offer-to");
    const requestFromField = document.querySelector("#request-from");
    const requestToField = document.querySelector("#request-to");

    const offerFromLat = document.querySelector('input[name="offer_from_lat"]');
    const offerFromLng = document.querySelector('input[name="offer_from_lng"]');
    const offerToLat = document.querySelector('input[name="offer_to_lat"]');
    const offerToLng = document.querySelector('input[name="offer_to_lng"]');

    const requestFromLat = document.querySelector(
      'input[name="request_from_lat"]'
    );
    const requestFromLng = document.querySelector(
      'input[name="request_from_lng"]'
    );
    const requestToLat = document.querySelector('input[name="request_to_lat"]');
    const requestToLng = document.querySelector('input[name="request_to_lng"]');

    const fromMarker = L.marker(DEFAULT_CENTER, { draggable: false });
    const toMarker = L.marker(DEFAULT_CENTER, { draggable: false });

    // Добавяме маркерите когато за първи път се ползват
    let fromMarkerAdded = false;
    let toMarkerAdded = false;

    function setFieldValue(field, value) {
      if (field) field.value = value;
    }

    function setLatLngInputs(lat, lng, which) {
      if (which === "from") {
        setFieldValue(offerFromLat, lat);
        setFieldValue(offerFromLng, lng);
        setFieldValue(requestFromLat, lat);
        setFieldValue(requestFromLng, lng);
      } else {
        setFieldValue(offerToLat, lat);
        setFieldValue(offerToLng, lng);
        setFieldValue(requestToLat, lat);
        setFieldValue(requestToLng, lng);
      }
    }

    function reverseGeocode(lat, lng, callback) {
      const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&accept-language=bg`;
      // В браузъра НЕ може да се слага User-Agent header – това чупи fetch().
      // Оставяме Nominatim със стандартния UA и само обработваме резултата.
      fetch(url)
        .then((res) => {
          if (!res.ok) {
            throw new Error(`Nominatim HTTP ${res.status}`);
          }
          return res.json();
        })
        .then((data) => {
          let label =
            (data.address &&
              (data.address.village ||
                data.address.town ||
                data.address.city)) ||
            data.display_name ||
            `${lat.toFixed(5)}, ${lng.toFixed(5)}`;

          if (typeof callback === "function") {
            callback(label);
          }
        })
        .catch((err) => {
          console.warn("VillageRide: reverse geocoding failed:", err);
          if (typeof callback === "function") {
            callback(`${lat.toFixed(5)}, ${lng.toFixed(5)}`);
          }
        });
    }

    map.on("click", (ev) => {
      const { lat, lng } = ev.latlng;
      console.log("VillageRide map click:", currentMode, lat, lng);

      if (currentMode === "from") {
        if (!fromMarkerAdded) {
          fromMarker.addTo(map);
          fromMarkerAdded = true;
        }
        fromMarker.setLatLng(ev.latlng);
      } else {
        if (!toMarkerAdded) {
          toMarker.addTo(map);
          toMarkerAdded = true;
        }
        toMarker.setLatLng(ev.latlng);
      }

      setLatLngInputs(lat, lng, currentMode);

      reverseGeocode(lat, lng, (label) => {
        if (currentMode === "from") {
          setFieldValue(offerFromField, label);
          setFieldValue(requestFromField, label);
        } else {
          setFieldValue(offerToField, label);
          setFieldValue(requestToField, label);
        }
      });
    });
  } catch (err) {
    console.error("VillageRide: map initialization failed:", err);
  }
});
