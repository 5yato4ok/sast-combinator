import React from 'react';

export default function ChannelPartnerDetails({ params }: { params: { id: string } }) {
	const allSubChannelPartners = canSwitchToThisAccount ? await fetchAllSubChannelPartners(params.id) : [];
	const subCpNames = Object.fromEntries(allSubChannelPartners.map((cp) => [cp.id, cp.name]));

	const allChildOrganizations = canSwitchToThisAccount ? await fetchAllChildOrganizations(params.id) : [];
	const orgNames = Object.fromEntries(allChildOrganizations.map((org) => [org.id, org.name]));

	return orgNames || subCpNames;
}
