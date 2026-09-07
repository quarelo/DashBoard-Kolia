import { apiRequest, setToken } from "../lib/api";
import type { AuthUser, LoginResponse, Role } from "../types";

export interface RegisterInput {
  name: string;
  email: string;
  role: Role;
  password: string;
}

export const authService = {
  async login(email: string, password: string): Promise<AuthUser> {
    const res = await apiRequest<LoginResponse>("/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    setToken(res.access_token);
    return authService.me();
  },

  async register(input: RegisterInput): Promise<void> {
    await apiRequest<{ message: string }>("/register", {
      method: "POST",
      body: input,
      auth: false,
    });
  },

  me(): Promise<AuthUser> {
    return apiRequest<AuthUser>("/me");
  },

  logout(): void {
    setToken(null);
  },
};

export const roleLabels: Record<Role, string> = {
  SALES_DIRECTOR: "Diretor Comercial",
  USER: "Usuário",
};
