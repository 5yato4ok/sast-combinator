import React, { useEffect } from 'react';

export function TiersForm() {
  const tiers = [{ tier: { id: 1 } }];
  const initialTiers = [1];
  const tierAdditionalInfo: Record<number, unknown> = {};
  const isLoadingTierAdditionalInfo: Record<number, boolean> = {};
  const setLoadingTierAdditionalInfo = (_updater: unknown) => {};
  const setTierAdditionalInfo = (_updater: unknown) => {};
  const rootChannelPartner = { id: 'root' };
  const individualCpOrOrg = { id: 'child' };
  const addTiersToSubChannelPartner = async (_root: string, _id: string, _items: number[]) => {};
  const removeTierFromSubChannelPartner = async (_root: string, _id: string, _tier: number, _commit: boolean) => ({ ok: true });
  const batchUpdatePromises = async (_promises: unknown[], _limit: number) => {};
  const onNext = () => {};
  const selected = [1];

  const checkTiers = async () => {
    for (const item of tiers) {
      const tierId = item.tier.id;
      const isSelected = initialTiers.includes(tierId);
      const alreadyHasInfo = !!tierAdditionalInfo[tierId];
      const currentlyLoading = isLoadingTierAdditionalInfo[tierId];

      if (isSelected && !alreadyHasInfo && !currentlyLoading) {
        try {
          setLoadingTierAdditionalInfo((prev) => ({ ...prev, [tierId]: true }));
          const commitChanges = false;
          const res = await removeTierFromSubChannelPartner(rootChannelPartner.id, individualCpOrOrg.id, tierId, commitChanges);
          if (res) {
            setTierAdditionalInfo((prev) => ({ ...prev, [tierId]: res }));
          }
        } catch (error) {
          console.error(`Error checking tier ${tierId}:`, error);
        } finally {
          setLoadingTierAdditionalInfo((prev) => ({ ...prev, [tierId]: false }));
        }
      }
    }
  };

  const handleSaveAndProceedClick = async () => {
    const newSelections = selected.filter((item) => !initialTiers?.includes(item));
    const removed = initialTiers ? initialTiers.filter((item) => !selected.includes(item)) : [];

    try {
      await addTiersToSubChannelPartner(rootChannelPartner.id, individualCpOrOrg.id, newSelections);
    } catch (e) {
      console.error('Error in Change Tiers for addTiersToSubChannelPartner', e);
    }

    try {
      const commitChanges = true;
      const updatePromises = removed.map((item) => () =>
        removeTierFromSubChannelPartner(rootChannelPartner.id, individualCpOrOrg?.id, item, commitChanges)
      );
      await batchUpdatePromises(updatePromises as any, 2);
    } catch (e) {
      console.error('Error in Change Tiers for removeTierFromASubChannelPartner', e);
    }

    onNext();
  };

  useEffect(() => {
    void checkTiers();
  }, []);

  return <button onClick={() => { void handleSaveAndProceedClick(); }}>Save tiers</button>;
}
