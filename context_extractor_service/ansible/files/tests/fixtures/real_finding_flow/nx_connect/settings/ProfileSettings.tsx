import { useForm, SubmitHandler } from 'react-hook-form';

type ProfileFormValues = { email: string };

export default function ProfileSettings() {
	const { register } = useForm<ProfileFormValues>();
	const onSubmit: SubmitHandler<ProfileFormValues> = (data) => console.log(data);
	return register && onSubmit;
}
