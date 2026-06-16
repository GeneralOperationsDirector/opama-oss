import React, { useState, useEffect } from "react";
import { Images, Plus } from "lucide-react";
import Button from "../../shared/atoms/Button";
import { api } from "../../lib/api";
import type { Showcase } from "../../types";

interface AddToShowcaseButtonProps {
  userId: number;
  cardId: string;
  onSuccess?: (showcaseTitle: string) => void;
  onError?: (message: string) => void;
  size?: "sm" | "md";
  variant?: "default" | "ghost";
}

export default function AddToShowcaseButton({
  userId,
  cardId,
  onSuccess,
  onError,
  size = "sm",
  variant = "ghost",
}: AddToShowcaseButtonProps) {
  const [showcases, setShowcases] = useState<Showcase[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (showDropdown && showcases.length === 0) {
      loadShowcases();
    }
  }, [showDropdown]);

  const loadShowcases = async () => {
    try {
      const data = await api<Showcase[]>(`/showcases`);
      setShowcases(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load showcases";
      onError?.(msg);
    }
  };

  const addToShowcase = async (showcaseId: number, showcaseTitle: string) => {
    setLoading(true);
    try {
      await api(`/showcases/${showcaseId}/cards`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ card_id: cardId, quantity: 1 }),
      });
      onSuccess?.(showcaseTitle);
      setShowDropdown(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to add to showcase";
      onError?.(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative">
      <Button
        size={size}
        variant={variant}
        onClick={() => setShowDropdown(!showDropdown)}
        disabled={loading}
        title="Add to Showcase"
      >
        <Images className="w-4 h-4" />
        {size === "md" && <span className="hidden sm:inline ml-1">Showcase</span>}
      </Button>

      {showDropdown && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setShowDropdown(false)}
          />

          {/* Dropdown */}
          <div className="absolute right-0 mt-1 w-64 bg-white rounded-lg shadow-lg border border-gray-200 z-20 max-h-80 overflow-y-auto">
            <div className="p-2">
              <div className="text-xs font-medium text-gray-500 px-2 py-1">
                Add to Showcase
              </div>

              {showcases.length === 0 ? (
                <div className="px-2 py-4 text-sm text-gray-500 text-center">
                  No showcases yet.
                  <br />
                  Create one in the Showcase tab!
                </div>
              ) : (
                <div className="space-y-1">
                  {showcases.map((showcase) => (
                    <button
                      key={showcase.id}
                      onClick={() => addToShowcase(showcase.id, showcase.title)}
                      disabled={loading}
                      className="w-full text-left px-2 py-2 rounded hover:bg-gray-100 text-sm transition-colors disabled:opacity-50"
                    >
                      <div className="font-medium">{showcase.title}</div>
                      {showcase.description && (
                        <div className="text-xs text-gray-500 truncate">
                          {showcase.description}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
