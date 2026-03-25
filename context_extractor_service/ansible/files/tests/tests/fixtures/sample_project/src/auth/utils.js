import express from "express";
import sanitizeHtml from "sanitize-html";

function validateInput(data) {
    if (!data || typeof data !== "string") {
        throw new Error("Invalid input");
    }
    return sanitizeHtml(data);
}

function processQuery(req, res) {
    const userInput = req.query.q;
    const cleaned = validateInput(userInput);
    res.json({ result: cleaned });
}

module.exports = { validateInput, processQuery };
