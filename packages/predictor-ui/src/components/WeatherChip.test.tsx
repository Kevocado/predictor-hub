import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WeatherChip, weatherSentence, type Conditions, type WeatherKind } from "./WeatherChip";

describe("WeatherChip", () => {
  it("says the sky and the temperature in words", () => {
    render(<WeatherChip conditions={{ kind: "rain", temp_f: 50, wind_mph: 8, precip_pct: 70 }} />);
    expect(screen.getByTestId("weather-chip")).toHaveTextContent("Rain · 50°F · 70% chance");
  });

  it("names wind only when it matters", () => {
    expect(weatherSentence({ kind: "clear", temp_f: 61, wind_mph: 9 })).toBe("Clear · 61°F");
    expect(weatherSentence({ kind: "clear", temp_f: 61, wind_mph: 22 })).toBe("Clear · 61°F · 22 mph wind");
  });

  it("a dome says indoors and no temperature", () => {
    render(<WeatherChip conditions={{ kind: "dome", temp_f: 72, wind_mph: 30 }} />);
    expect(screen.getByTestId("weather-chip")).toHaveTextContent(/^Indoors$/);
  });

  it("renders nothing without conditions or with an unknown kind", () => {
    const { container, rerender } = render(<WeatherChip conditions={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<WeatherChip conditions={{ kind: "tornado" } as unknown as Conditions} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<WeatherChip conditions={{ kind: "toString" } as unknown as Conditions} />);  // inherited, not ours
    expect(container).toBeEmptyDOMElement();
  });

  it.each(["clear", "partly", "cloudy", "fog", "rain", "snow", "storm", "dome"] as WeatherKind[])("%s draws an icon that is hidden from assistive tech", (kind) => {
    render(<WeatherChip conditions={{ kind }} />);
    const svg = screen.getByTestId("weather-chip").querySelector("svg")!;
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg.childElementCount).toBeGreaterThan(0);
  });

  it("a rain chance under 30% is not announced", () => {
    expect(weatherSentence({ kind: "rain", temp_f: 50, precip_pct: 20 })).toBe("Rain · 50°F");
  });

  it("a rain chance is not announced when the sky is dry", () => {
    // A 90% chance of rain under "Clear" is a forecast about a different hour, or
    // a bug upstream. Either way the chip must not print a number that contradicts
    // the word beside it, so the percentage is only ever announced for a wet sky.
    expect(weatherSentence({ kind: "clear", temp_f: 61, precip_pct: 90 })).toBe("Clear · 61°F");
  });

  it("a missing or unusable figure is absent rather than a dash", () => {
    // Spec §6: an absent market renders nothing. The same rule here — a chip
    // reading "Rain · — · " would be a row with placeholders in it.
    expect(weatherSentence({ kind: "rain" })).toBe("Rain");
    expect(weatherSentence({ kind: "rain", temp_f: null, wind_mph: null, precip_pct: null })).toBe("Rain");
  });

  it("a temperature is rounded to the whole degree it is drawn at", () => {
    expect(weatherSentence({ kind: "clear", temp_f: 61.4 })).toBe("Clear · 61°F");
    expect(weatherSentence({ kind: "clear", temp_f: 61.6 })).toBe("Clear · 62°F");
  });
});