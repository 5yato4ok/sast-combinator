import { useForm, SubmitHandler } from 'react-hook-form';

type IFormInput = { name: string };

export default function AddServiceForm() {
	const { register } = useForm<IFormInput>();
	const onSubmit: SubmitHandler<IFormInput> = (data) => console.log(data);
	return register && onSubmit;
}
