package com.example.auth;

import java.sql.Connection;
import java.sql.PreparedStatement;

public class Handler {

    @RequestMapping("/api/login")
    public String login(String username, String password) {
        Connection conn = getConnection();
        PreparedStatement stmt = conn.prepareStatement(
            "SELECT * FROM users WHERE name = ? AND pass = ?"
        );
        stmt.setString(1, username);
        stmt.setString(2, password);
        return stmt.executeQuery().toString();
    }

    private Connection getConnection() {
        return null;
    }
}
