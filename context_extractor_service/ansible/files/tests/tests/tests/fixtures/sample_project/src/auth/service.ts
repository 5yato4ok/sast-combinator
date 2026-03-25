import { Injectable } from "@angular/core";
import { HttpClient } from "@angular/common/http";
import * as sanitizeHtml from "sanitize-html";

@Injectable({
  providedIn: "root",
})
export class AuthService {
  constructor(private http: HttpClient) {}

  getUserData(userId: string) {
    const sanitized = sanitizeHtml(userId);
    const url = `/api/users/${sanitized}`;
    return this.http.get(url);
  }

  validateToken(token: string): boolean {
    return token.length > 0;
  }
}
