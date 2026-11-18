"use strict";

const bag = document.getElementById("store-bag");
const quantity = document.getElementById("shop-quantity");
const status = document.getElementById("shop-bag-status");
let itemCount = 0;

bag.addEventListener("submit", (event) => {
  event.preventDefault();
  itemCount += Number(quantity.value);
  status.textContent = `Demo bag: ${itemCount} ${itemCount === 1 ? "item" : "items"}.`;
});
