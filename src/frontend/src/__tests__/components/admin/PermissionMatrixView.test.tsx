import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import React from "react";
import { PermissionMatrixView } from "../../../components/admin/PermissionMatrixView";
import type { RoleDetail } from "../../../types/admin";

/**
 * Tests for PermissionMatrixView grid rendering and checkmark display.
 *
 * Validates: Requirements 10.2
 */

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const systemAdminRole: RoleDetail = {
  id: 1,
  name: "system_admin",
  description: "Full system access",
  is_system: true,
  permissions: {
    documents: ["create", "read", "update", "delete", "approve"],
    workflows: ["create", "read", "update", "delete", "approve"],
    users: ["create", "read", "update", "delete", "approve"],
    audit_logs: ["create", "read", "update", "delete", "approve"],
    templates: ["create", "read", "update", "delete", "approve"],
    training: ["create", "read", "update", "delete", "approve"],
    signatures: ["create", "read", "update", "delete", "approve"],
    system_config: ["create", "read", "update", "delete", "approve"],
  },
  user_count: 2,
};

const viewerRole: RoleDetail = {
  id: 5,
  name: "viewer",
  description: "Read-only access",
  is_system: true,
  permissions: {
    documents: ["read"],
    workflows: ["read"],
    templates: ["read"],
    training: ["read"],
  },
  user_count: 8,
};

const memberRole: RoleDetail = {
  id: 4,
  name: "member",
  description: "Standard member",
  is_system: true,
  permissions: {
    documents: ["create", "read", "update"],
    training: ["create", "read", "update"],
    workflows: ["read"],
    templates: ["read"],
  },
  user_count: 15,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PermissionMatrixView", () => {
  afterEach(() => {
    cleanup();
  });

  describe("Grid rendering", () => {
    it("renders table with correct aria-label", () => {
      render(<PermissionMatrixView role={systemAdminRole} />);

      expect(screen.getByLabelText("Permission matrix for system_admin")).toBeDefined();
    });

    it("renders all resource type rows", () => {
      render(<PermissionMatrixView role={systemAdminRole} />);

      expect(screen.getByText("Documents")).toBeDefined();
      expect(screen.getByText("Workflows")).toBeDefined();
      expect(screen.getByText("Users")).toBeDefined();
      expect(screen.getByText("Audit Logs")).toBeDefined();
      expect(screen.getByText("Templates")).toBeDefined();
      expect(screen.getByText("Training")).toBeDefined();
      expect(screen.getByText("Signatures")).toBeDefined();
      expect(screen.getByText("System Config")).toBeDefined();
    });

    it("renders all action column headers", () => {
      render(<PermissionMatrixView role={systemAdminRole} />);

      expect(screen.getByText("Create")).toBeDefined();
      expect(screen.getByText("Read")).toBeDefined();
      expect(screen.getByText("Update")).toBeDefined();
      expect(screen.getByText("Delete")).toBeDefined();
      expect(screen.getByText("Approve")).toBeDefined();
    });
  });

  describe("Checkmark display", () => {
    it("shows granted indicators for all permissions of system_admin", () => {
      render(<PermissionMatrixView role={systemAdminRole} />);

      // system_admin has all permissions (8 resources × 5 actions = 40 granted)
      const grantedLabels = screen.getAllByLabelText(/granted for/);
      expect(grantedLabels.length).toBe(40);
    });

    it("shows denied indicators for missing permissions of viewer", () => {
      render(<PermissionMatrixView role={viewerRole} />);

      // viewer has read on 4 resources = 4 granted
      const grantedLabels = screen.getAllByLabelText(/granted for/);
      expect(grantedLabels.length).toBe(4);

      // The rest should be denied (8 resources × 5 actions - 4 = 36 denied)
      const deniedLabels = screen.getAllByLabelText(/denied for/);
      expect(deniedLabels.length).toBe(36);
    });

    it("correctly shows mixed permissions for member role", () => {
      render(<PermissionMatrixView role={memberRole} />);

      // member: documents(create,read,update), training(create,read,update), workflows(read), templates(read)
      // = 3 + 3 + 1 + 1 = 8 granted
      const grantedLabels = screen.getAllByLabelText(/granted for/);
      expect(grantedLabels.length).toBe(8);
    });

    it("shows correct aria-label for granted permission", () => {
      render(<PermissionMatrixView role={viewerRole} />);

      expect(screen.getByLabelText("Read granted for Documents")).toBeDefined();
    });

    it("shows correct aria-label for denied permission", () => {
      render(<PermissionMatrixView role={viewerRole} />);

      expect(screen.getByLabelText("Create denied for Documents")).toBeDefined();
    });
  });
});
