/**
 * API service layer.
 *
 * All HTTP calls go through this module. Components never import Axios
 * directly — they call these functions instead, keeping the API base URL
 * and error handling in one place.
 */

import axios from "axios";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  timeout: 15000,
});

export async function getSets() {
  const { data } = await http.get("/sets");
  return data;
}

export async function getSet(setId) {
  const { data } = await http.get(`/sets/${setId}`);
  return data;
}

export async function getCardsForSet(setId) {
  const { data } = await http.get(`/sets/${setId}/cards`);
  return data;
}

export async function getCard(cardId) {
  const { data } = await http.get(`/cards/${cardId}`);
  return data;
}
