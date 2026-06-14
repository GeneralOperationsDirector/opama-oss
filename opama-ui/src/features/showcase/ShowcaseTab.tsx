import React, { useEffect, useState, useCallback } from "react";
import { Plus, Edit2, Trash2, Globe, Lock, Save, X } from "lucide-react";
import ConfirmModal from "../../shared/atoms/ConfirmModal";
import Section from "../../shared/atoms/Section";
import Button from "../../shared/atoms/Button";
import CardTile from "../../shared/CardTile";
import { api } from "../../lib/api";
import type { Showcase, ShowcaseWithCards, ShowcaseCardItem } from "../../types";

interface ShowcaseTabProps {
  userId: number;
  onOpenDetails: (cardId: string) => void;
  onToast: (message: string, type?: "success" | "error" | "info") => void;
}

export default function ShowcaseTab({ userId, onOpenDetails, onToast }: ShowcaseTabProps) {
  const [showcases, setShowcases] = useState<Showcase[]>([]);
  const [activeShowcaseId, setActiveShowcaseId] = useState<number | null>(null);
  const [activeShowcase, setActiveShowcase] = useState<ShowcaseWithCards | null>(null);
  const [loading, setLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingShowcase, setEditingShowcase] = useState(false);
  const [cardCounts, setCardCounts] = useState<Map<number, number>>(new Map());
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Load showcases on mount
  useEffect(() => {
    loadShowcases();
  }, [userId]);

  // Load active showcase when selection changes
  useEffect(() => {
    if (activeShowcaseId) {
      loadShowcase(activeShowcaseId);
    } else {
      setActiveShowcase(null);
    }
  }, [activeShowcaseId]);

  const loadShowcases = async () => {
    try {
      const data = await api<Showcase[]>(`/showcases`);
      setShowcases(data);

      // Auto-select first showcase if none selected
      if (data.length > 0 && !activeShowcaseId) {
        setActiveShowcaseId(data[0].id);
      }
    } catch (err) {
      onToast("Failed to load showcases", "error");
    }
  };

  const loadShowcase = async (id: number) => {
    setLoading(true);
    try {
      const data = await api<ShowcaseWithCards>(`/showcases/${id}`);
      setActiveShowcase(data);

      // Update card count for this showcase
      setCardCounts((prev) => new Map(prev).set(id, data.cards.length));
    } catch (err) {
      onToast("Failed to load showcase", "error");
    } finally {
      setLoading(false);
    }
  };

  const createShowcase = async (title: string, description: string, isPublic: boolean) => {
    try {
      const newShowcase = await api<Showcase>(`/showcases?user_id=${userId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, description, is_public: isPublic }),
      });

      setShowcases((prev) => [newShowcase, ...prev]);
      setActiveShowcaseId(newShowcase.id);
      setShowCreateModal(false);
      onToast("Showcase created!", "success");
    } catch (err) {
      onToast("Failed to create showcase", "error");
    }
  };

  const updateShowcase = async (updates: { title?: string; description?: string; is_public?: boolean }) => {
    if (!activeShowcaseId) return;

    try {
      const updated = await api<Showcase>(`/showcases/${activeShowcaseId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });

      setShowcases((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      if (activeShowcase) {
        setActiveShowcase({ ...activeShowcase, showcase: updated });
      }
      setEditingShowcase(false);
      onToast("Showcase updated!", "success");
    } catch (err) {
      onToast("Failed to update showcase", "error");
    }
  };

  const deleteShowcase = async () => {
    if (!activeShowcaseId) return;
    try {
      await api(`/showcases/${activeShowcaseId}`, { method: "DELETE" });
      setShowcases((prev) => prev.filter((s) => s.id !== activeShowcaseId));
      setActiveShowcaseId(showcases[0]?.id || null);
      onToast("Showcase deleted", "success");
    } catch (err) {
      onToast("Failed to delete showcase", "error");
    }
  };

  const removeCard = async (cardItemId: number) => {
    if (!activeShowcaseId) return;

    try {
      await api(`/showcases/${activeShowcaseId}/cards/${cardItemId}`, { method: "DELETE" });
      await loadShowcase(activeShowcaseId);
      onToast("Card removed from showcase", "success");
    } catch (err) {
      onToast("Failed to remove card", "error");
    }
  };

  const updateCardQuantity = async (cardItemId: number, quantity: number) => {
    if (!activeShowcaseId) return;

    try {
      await api(`/showcases/${activeShowcaseId}/cards/${cardItemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quantity }),
      });
      await loadShowcase(activeShowcaseId);
      onToast("Quantity updated", "success");
    } catch (err) {
      onToast("Failed to update quantity", "error");
    }
  };

  const togglePublic = () => {
    if (activeShowcase) {
      updateShowcase({ is_public: !activeShowcase.showcase.is_public });
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* Sidebar: Showcase List */}
      <div className="lg:col-span-1">
        <Section
          title="My Showcases"
          className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)]"
          actions={
            <Button size="sm" onClick={() => setShowCreateModal(true)}>
              <Plus className="w-4 h-4" />
            </Button>
          }
        >
          <div className="space-y-2">
            {showcases.length === 0 ? (
              <div className="text-center py-12 px-4">
                <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-lg p-6 border-2 border-dashed border-indigo-200">
                  <Plus className="w-8 h-8 text-indigo-400 mx-auto mb-3" />
                  <p className="text-sm font-medium text-gray-700 mb-1">
                    No showcases yet
                  </p>
                  <p className="text-xs text-gray-500 mb-4">
                    Create your first showcase to display your collection!
                  </p>
                  <Button
                    size="sm"
                    onClick={() => setShowCreateModal(true)}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 text-white"
                  >
                    <Plus className="w-4 h-4" />
                    Create Showcase
                  </Button>
                </div>
              </div>
            ) : (
              showcases.map((showcase) => {
                const isActive = activeShowcaseId === showcase.id;
                const cardCount = cardCounts.get(showcase.id);

                return (
                  <button
                    key={showcase.id}
                    onClick={() => setActiveShowcaseId(showcase.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg border-2 transition-all duration-200 ${
                      isActive
                        ? "bg-indigo-600 text-white border-indigo-600 shadow-lg shadow-indigo-200"
                        : "bg-white hover:bg-indigo-50 hover:border-indigo-300 border-gray-200"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold truncate">{showcase.title}</span>
                          {cardCount !== undefined && (
                            <span
                              className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                                isActive
                                  ? "bg-indigo-500 text-white"
                                  : "bg-gray-100 text-gray-600"
                              }`}
                            >
                              {cardCount}
                            </span>
                          )}
                        </div>
                        {showcase.description && (
                          <div
                            className={`text-xs truncate mt-1 ${
                              isActive ? "text-indigo-100" : "text-gray-500"
                            }`}
                          >
                            {showcase.description}
                          </div>
                        )}
                      </div>
                      {showcase.is_public && (
                        <Globe
                          className={`w-4 h-4 flex-shrink-0 ${
                            isActive ? "text-green-300" : "text-green-500"
                          }`}
                          title="Public"
                        />
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </Section>
      </div>

      {/* Main Area: Showcase Details */}
      <div className="lg:col-span-3">
        {!activeShowcase ? (
          <Section title={showcases.length === 0 ? "Welcome to Showcases" : "Select a Showcase"}>
            <div className="text-center py-20 px-4">
              <div className="max-w-md mx-auto">
                <div className="bg-gradient-to-br from-purple-50 to-indigo-50 rounded-full w-24 h-24 flex items-center justify-center mx-auto mb-6">
                  <Globe className="w-12 h-12 text-indigo-600" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-3">
                  {showcases.length === 0
                    ? "Share Your Collection with the World"
                    : "Choose a showcase to view"}
                </h3>
                <p className="text-gray-500 mb-6">
                  {showcases.length === 0
                    ? "Showcases let you display your favorite cards, organize trades, or share your collection publicly."
                    : "Select a showcase from the sidebar to view and manage its cards."}
                </p>
                {showcases.length === 0 && (
                  <Button
                    onClick={() => setShowCreateModal(true)}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white"
                  >
                    <Plus className="w-5 h-5" />
                    Create Your First Showcase
                  </Button>
                )}
              </div>
            </div>
          </Section>
        ) : (
          <Section
            title={activeShowcase.showcase.title}
            subtitle={activeShowcase.showcase.description || undefined}
            actions={
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant={activeShowcase.showcase.is_public ? "default" : "ghost"}
                  onClick={togglePublic}
                  title={activeShowcase.showcase.is_public ? "Public (click to make private)" : "Private (click to make public)"}
                >
                  {activeShowcase.showcase.is_public ? (
                    <>
                      <Globe className="w-4 h-4" /> Public
                    </>
                  ) : (
                    <>
                      <Lock className="w-4 h-4" /> Private
                    </>
                  )}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditingShowcase(true)}>
                  <Edit2 className="w-4 h-4" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)}>
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            }
          >
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="text-center">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                  <p className="text-gray-500">Loading cards...</p>
                </div>
              </div>
            ) : activeShowcase.cards.length === 0 ? (
              <div className="text-center py-20 px-4">
                <div className="max-w-sm mx-auto">
                  <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-6">
                    <Plus className="w-10 h-10 text-indigo-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">
                    This showcase is empty
                  </h3>
                  <p className="text-gray-500 mb-6">
                    Start building your showcase by adding cards from your collection!
                  </p>
                  <div className="flex flex-col sm:flex-row gap-3 justify-center">
                    <Button
                      onClick={() => window.dispatchEvent(new CustomEvent('switchTab', { detail: 'catalog' }))}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white"
                    >
                      Browse Catalog
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => window.dispatchEvent(new CustomEvent('switchTab', { detail: 'inventory' }))}
                      className="border-2 border-gray-200 hover:border-indigo-300 hover:bg-indigo-50"
                    >
                      View Inventory
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-4 sm:grid-cols-3 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-2 gap-6 auto-rows-min content-start">
                {activeShowcase.cards.map((item) => (
                  <div
                    key={item.id}
                    className="relative group transition-transform duration-200 hover:scale-105 hover:z-10"
                  >
                    {/* Quantity Badge - Top Right */}
                    {item.quantity > 1 && (
                      <div className="absolute top-2 right-2 z-10 bg-indigo-600 text-white text-xs font-bold px-2 py-1 rounded-full shadow-lg border-2 border-white">
                        ×{item.quantity}
                      </div>
                    )}

                    {/* Notes Indicator - Top Left */}
                    {item.notes && (
                      <div
                        className="absolute top-2 left-2 z-10 bg-yellow-400 text-yellow-900 text-xs font-medium px-2 py-1 rounded-full shadow-md border-2 border-white cursor-help"
                        title={item.notes}
                      >
                        📝 Note
                      </div>
                    )}

                    <CardTile
                      cardLike={item.card || { id: item.card_id, name: item.card_id, set_id: "" }}
                      onOpenDetails={onOpenDetails}
                      fallbackId={item.card_id}
                      right={
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation();
                              removeCard(item.id);
                            }}
                            className="bg-white/90 backdrop-blur-sm text-red-600 hover:text-white hover:bg-red-600 shadow-lg border border-red-200"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      }
                    />
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}
      </div>

      {/* Create Showcase Modal */}
      {showCreateModal && (
        <CreateShowcaseModal
          onClose={() => setShowCreateModal(false)}
          onCreate={createShowcase}
        />
      )}

      {/* Edit Showcase Modal */}
      {editingShowcase && activeShowcase && (
        <EditShowcaseModal
          showcase={activeShowcase.showcase}
          onClose={() => setEditingShowcase(false)}
          onSave={updateShowcase}
        />
      )}

      {/* Delete Confirm Modal */}
      {confirmDelete && (
        <ConfirmModal
          title="Delete showcase?"
          message={`"${showcases.find((s) => s.id === activeShowcaseId)?.title}" will be permanently deleted.`}
          confirmLabel="Delete"
          destructive
          onConfirm={() => { setConfirmDelete(false); deleteShowcase(); }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </div>
  );
}

// Create Showcase Modal
function CreateShowcaseModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (title: string, description: string, isPublic: boolean) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    onCreate(title.trim(), description.trim(), isPublic);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-md w-full p-6">
        <h2 className="text-xl font-bold mb-4">Create Showcase</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Full Art Cards, For Trade, Vintage Collection"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add a description..."
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              rows={3}
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is-public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              className="rounded"
            />
            <label htmlFor="is-public" className="text-sm">
              Make this showcase public (visible on your profile)
            </label>
          </div>
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!title.trim()}>
              Create Showcase
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Edit Showcase Modal
function EditShowcaseModal({
  showcase,
  onClose,
  onSave,
}: {
  showcase: Showcase;
  onClose: () => void;
  onSave: (updates: { title?: string; description?: string; is_public?: boolean }) => void;
}) {
  const [title, setTitle] = useState(showcase.title);
  const [description, setDescription] = useState(showcase.description || "");
  const [isPublic, setIsPublic] = useState(showcase.is_public);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    onSave({
      title: title.trim(),
      description: description.trim(),
      is_public: isPublic,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-md w-full p-6">
        <h2 className="text-xl font-bold mb-4">Edit Showcase</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
              rows={3}
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="edit-is-public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              className="rounded"
            />
            <label htmlFor="edit-is-public" className="text-sm">
              Make this showcase public (visible on your profile)
            </label>
          </div>
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!title.trim()}>
              <Save className="w-4 h-4" /> Save Changes
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
